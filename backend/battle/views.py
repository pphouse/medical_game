"""対戦モード（早押し）API (spec フェーズ4).

進行:
1. ホストがルーム作成 → 6桁コードを共有 → 参加 → ホストが開始
2. start 時に全 BattleRound を先に作成し、ラウンド1の revealed_at を設定
3. 出題配信は Supabase Realtime（battle_battleround の変更購読）。
   Realtime なし環境向けに GET .../state/ のポーリングでも完全に動く
4. 早押しは Supabase RPC `claim_buzz`（clock_timestamp() でサーバ時刻確定）。
   開発用フォールバックとして POST /rounds/{id}/buzz/ も同じ意味論で提供
   （行ロックで直列化し DB 時刻で記録。クライアント時刻は一切信用しない）
5. rank=1 から順に回答権。誤答で次順位へ。正解 or 全員誤答 or 制限時間で
   ラウンドを閉じ、次ラウンドの revealed_at を設定
6. いつでも POST .../leave/ で離脱できる。待機中は参加者から抜けるだけ
   （ホストなら次の参加者に引き継ぐ）。対戦中はスコアを凍結し、同じ
   ランク帯のAI（人間には見分けが付かない偽名・偽の所属大学つき）が
   即座に代役として入る。無応答が続いた参加者（PARTICIPANT_TIMEOUT_SECONDS
   秒、既存の「オフライン」判定と同じ閾値）も、他の参加者のポーリングを
   きっかけに自動で同じ扱いになる
"""

import datetime
import secrets

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.ranktier import compute_tier
from quiz.models import AnswerHistory, Question
from quiz.serializers import QuestionSerializer
from quiz.views import update_review_schedule

from .ai import DEFAULT_AI_TIER, create_disguised_ai_profile, simulate_ai_turn
from .matchmaking import (
    create_ticket,
    escalate_to_ai_if_timed_out,
    opponent_profile_payload,
    try_match,
)
from .models import BattleBuzz, BattleParticipant, BattleRoom, BattleRound, MatchmakingTicket
from .scoring import (
    PARTICIPANT_TIMEOUT_SECONDS,
    ROUND_TIME_LIMIT_SECONDS,
    apply_score,
    battle_points_delta,
)

MIN_PARTICIPANTS = 2
MAX_PARTICIPANTS = 8


def get_room(code):
    return get_object_or_404(BattleRoom, room_code=code)


def require_participant(room, profile):
    participant = room.participants.filter(user=profile).first()
    if participant is None:
        raise exceptions.PermissionDenied("このルームの参加者ではありません。")
    return participant


def open_round(room):
    return (
        room.rounds.filter(closed_at__isnull=True)
        .select_related("question")
        .order_by("round_number")
        .first()
    )


def finalize_room_points(room):
    """ルーム終了時に一度だけ対戦ランクポイントを確定する (spec: 対戦＋模試の
    合算ポイントでSS〜Dランク)。AI 参加者（accounts.Profile.is_ai）は対象外。"""
    participants = list(
        room.participants.select_related("user").order_by("-score", "id")
    )
    n = len(participants)
    prev_score, prev_rank = None, 0
    for i, participant in enumerate(participants, start=1):
        rank = prev_rank if participant.score == prev_score else i
        prev_score, prev_rank = participant.score, rank
        if participant.user.is_ai:
            continue
        delta = battle_points_delta(rank, n)
        participant.points_delta = delta
        participant.save(update_fields=["points_delta"])
        profile = participant.user
        profile.points = max(0, profile.points + delta)
        profile.ranked_matches += 1
        profile.save(update_fields=["points", "ranked_matches"])


def close_round_and_advance(round_):
    """ラウンドを閉じ、次ラウンドの出題 or ルーム終了処理を行う。"""
    now = timezone.now()
    round_.closed_at = now
    round_.save(update_fields=["closed_at"])
    next_round = (
        round_.room.rounds.filter(closed_at__isnull=True)
        .order_by("round_number")
        .first()
    )
    if next_round:
        next_round.revealed_at = now
        next_round.save(update_fields=["revealed_at"])
    else:
        round_.room.status = BattleRoom.Status.FINISHED
        round_.room.save(update_fields=["status"])
        finalize_room_points(round_.room)


def enforce_round_progress(room):
    """制限時間切れ・全員誤答（離脱者はスキップ扱い）を遅延評価で処理する。"""
    round_ = open_round(room)
    if round_ is None or round_.revealed_at is None:
        return
    now = timezone.now()
    deadline = round_.revealed_at + datetime.timedelta(seconds=ROUND_TIME_LIMIT_SECONDS)
    if now >= deadline:
        close_round_and_advance(round_)
        return
    # 全員誤答チェック: 30秒以上応答のない参加者・離脱済みの参加者はスキップ扱い (spec 4-2)
    active_cutoff = now - datetime.timedelta(seconds=PARTICIPANT_TIMEOUT_SECONDS)
    active_ids = set(
        room.participants.filter(
            last_seen_at__gte=active_cutoff, left_at__isnull=True
        ).values_list("user_id", flat=True)
    )
    if not active_ids:
        return
    wrong_ids = set(
        round_.buzzes.filter(is_correct=False).values_list("profile_id", flat=True)
    )
    if active_ids <= wrong_ids:
        close_round_and_advance(round_)


def _replace_with_ai(room, participant):
    """参加者1人をスコアを凍結して退場させ、同じランク帯のAI（偽名・偽の
    所属大学つきで、人間には見分けが付かない）を即座に代役として入れる。"""
    if participant.left_at is not None:
        return
    tier = compute_tier(participant.user) or DEFAULT_AI_TIER
    participant.left_at = timezone.now()
    participant.save(update_fields=["left_at"])
    ai_profile, ai_tier = create_disguised_ai_profile(tier)
    BattleParticipant.objects.create(room=room, user=ai_profile, ai_tier=ai_tier)


def _finish_if_no_active_humans(room):
    """AI同士だけが残った対戦は誰も見ていないので、その場で打ち切る。"""
    current_status = (
        BattleRoom.objects.filter(pk=room.pk).values_list("status", flat=True).first()
    )
    if current_status != BattleRoom.Status.IN_PROGRESS:
        return
    has_active_human = room.participants.filter(
        left_at__isnull=True, user__is_ai=False
    ).exists()
    if has_active_human:
        return
    round_ = open_round(room)
    if round_ is not None:
        round_.closed_at = timezone.now()
        round_.save(update_fields=["closed_at"])
    room.status = BattleRoom.Status.FINISHED
    room.save(update_fields=["status"])
    finalize_room_points(room)


def replace_disconnected_participants(room):
    """無応答が続く参加者（既存の「オフライン」判定と同じ閾値）を、他の
    参加者のポーリングをきっかけに自動でAIへ入れ替える。"""
    cutoff = timezone.now() - datetime.timedelta(seconds=PARTICIPANT_TIMEOUT_SECONDS)
    stale = list(
        room.participants.select_related("user").filter(
            left_at__isnull=True, user__is_ai=False, last_seen_at__lt=cutoff
        )
    )
    for participant in stale:
        _replace_with_ai(room, participant)
    if stale:
        _finish_if_no_active_humans(room)


class RoomCreateView(APIView):
    """POST /api/battle/rooms/ — room_code は衝突リトライ付きで生成 (spec 4-2)."""

    def post(self, request):
        question_count = int(request.data.get("question_count", 10))
        if question_count not in (5, 10, 20):
            raise exceptions.ValidationError("question_count は 5 / 10 / 20 のみ")
        category = request.data.get("category", "") or ""

        room = None
        for _ in range(10):
            code = f"{secrets.randbelow(900000) + 100000}"
            try:
                room = BattleRoom.objects.create(
                    host=request.user,
                    room_code=code,
                    question_count=question_count,
                    category=category,
                )
                break
            except IntegrityError:
                continue
        if room is None:
            raise exceptions.APIException("ルームコードの生成に失敗しました。")

        BattleParticipant.objects.create(room=room, user=request.user)
        return Response({"room_code": room.room_code}, status=201)


class RoomJoinView(APIView):
    def post(self, request, code):
        room = get_room(code)
        if room.participants.filter(user=request.user).exists():
            return Response({"room_code": room.room_code})  # 再入室は冪等
        if room.status != BattleRoom.Status.WAITING:
            raise exceptions.ValidationError("この対戦はすでに開始されています。")
        if room.participants.count() >= MAX_PARTICIPANTS:
            raise exceptions.ValidationError("満室です。")
        BattleParticipant.objects.create(room=room, user=request.user)
        return Response({"room_code": room.room_code})


class RoomLeaveView(APIView):
    """POST /api/battle/rooms/{code}/leave/ — いつでも離脱できる。

    待機中: 参加者から抜けるだけ。ホストが抜けた場合は次の参加者に
    ホストを引き継ぎ、誰もいなくなったらルームごと削除する。
    対戦中: スコアを凍結して退場し、同じランク帯のAIが即座に代役として
    入る（他の参加者が対戦を続けられるように）。人間が誰もいなくなったら
    その場で対戦を打ち切る。
    """

    def post(self, request, code):
        room = get_room(code)
        participant = require_participant(room, request.user)
        if room.status == BattleRoom.Status.FINISHED:
            raise exceptions.ValidationError("この対戦はすでに終了しています。")

        if room.status == BattleRoom.Status.WAITING:
            was_host = participant.user_id == room.host_id
            participant.delete()
            remaining = list(room.participants.order_by("id"))
            if not remaining:
                room.delete()
            elif was_host:
                room.host = remaining[0].user
                room.save(update_fields=["host"])
        else:
            _replace_with_ai(room, participant)
            _finish_if_no_active_humans(room)

        return Response({"status": "left"})


def start_room(room):
    """問題を抽選し全 BattleRound を先に作って IN_PROGRESS にする (spec 4-2)。
    通常のホスト開始・クイックマッチ自動開始の両方から呼ばれる共通処理。"""
    if room.status != BattleRoom.Status.WAITING:
        raise exceptions.ValidationError("すでに開始されています。")
    if room.participants.count() < MIN_PARTICIPANTS:
        raise exceptions.ValidationError("対戦には2人以上の参加者が必要です。")

    # published かつ public からランダム抽出（分野フィルタ任意, spec 4-1）
    qs = Question.objects.published().filter(visibility=Question.Visibility.PUBLIC)
    if room.category:
        qs = qs.filter(category=room.category)
    questions = list(qs.order_by("?")[: room.question_count])
    if len(questions) < room.question_count:
        raise exceptions.ValidationError(
            f"出題できる問題が不足しています（{len(questions)}/{room.question_count}問）。"
        )

    now = timezone.now()
    with transaction.atomic():
        BattleRound.objects.bulk_create(
            BattleRound(
                room=room,
                question=question,
                round_number=i + 1,
                revealed_at=now if i == 0 else None,
            )
            for i, question in enumerate(questions)
        )
        room.status = BattleRoom.Status.IN_PROGRESS
        room.save(update_fields=["status"])


class RoomStartView(APIView):
    """ホストのみ。問題を抽選し全 BattleRound を先に作る (spec 4-2)."""

    def post(self, request, code):
        room = get_room(code)
        if room.host_id != request.user.id:
            raise exceptions.PermissionDenied("開始できるのはホストのみです。")
        start_room(room)
        return Response({"status": room.status})


class RoomStateView(APIView):
    """ポーリング用の完全な状態 (spec 4-1: Realtime が主、これはフォールバック).

    呼び出し自体を heartbeat として last_seen_at を更新する。
    """

    def get(self, request, code):
        room = get_room(code)
        participant = require_participant(room, request.user)
        BattleParticipant.objects.filter(pk=participant.pk).update(
            last_seen_at=timezone.now()
        )

        if room.status == BattleRoom.Status.IN_PROGRESS:
            replace_disconnected_participants(room)
            simulate_ai_turn(room)
            enforce_round_progress(room)
            room.refresh_from_db(fields=["status"])

        now = timezone.now()
        cutoff = now - datetime.timedelta(seconds=PARTICIPANT_TIMEOUT_SECONDS)
        participants = [
            {
                "display_name": p.user.display_name or "匿名ユーザー",
                "score": p.score,
                "is_me": p.user_id == request.user.id,
                "is_host": p.user_id == room.host_id,
                "connected": p.left_at is None and p.last_seen_at >= cutoff,
                "left": p.left_at is not None,
            }
            for p in room.participants.select_related("user").order_by("-score", "id")
        ]

        payload = {
            "room": {
                "room_code": room.room_code,
                "status": room.status,
                "question_count": room.question_count,
                "category": room.category or None,
            },
            "participants": participants,
            "round": None,
            "last_result": None,
        }

        round_ = open_round(room)
        if round_ and round_.revealed_at:
            buzzes = list(round_.buzzes.select_related("profile").order_by("rank"))
            answering = next((b for b in buzzes if b.is_correct is None), None)
            my_buzz = next((b for b in buzzes if b.profile_id == request.user.id), None)
            payload["round"] = {
                "id": round_.id,
                "number": round_.round_number,
                "total": room.question_count,
                "revealed_at": round_.revealed_at,
                "closes_at": round_.revealed_at
                + datetime.timedelta(seconds=ROUND_TIME_LIMIT_SECONDS),
                "question": QuestionSerializer(round_.question).data,
                "buzzes": [
                    {
                        "rank": b.rank,
                        "display_name": b.profile.display_name or "匿名ユーザー",
                        "is_correct": b.is_correct,
                        "is_me": b.profile_id == request.user.id,
                    }
                    for b in buzzes
                ],
                "answering_rank": answering.rank if answering else None,
                "i_am_answering": bool(
                    answering and answering.profile_id == request.user.id
                ),
                "my_buzz_rank": my_buzz.rank if my_buzz else None,
                "can_buzz": my_buzz is None,
            }

        last_closed = (
            room.rounds.filter(closed_at__isnull=False)
            .select_related("question")
            .order_by("-round_number")
            .first()
        )
        if last_closed:
            winner = (
                last_closed.buzzes.filter(is_correct=True)
                .select_related("profile")
                .first()
            )
            payload["last_result"] = {
                "number": last_closed.round_number,
                "correct_choice_key": last_closed.question.correct_choice_key,
                "explanation": last_closed.question.explanation,
                "winner": (winner.profile.display_name or "匿名ユーザー") if winner else None,
            }

        return Response(payload)


class BuzzView(APIView):
    """POST /api/battle/rounds/{id}/buzz/ — Django フォールバック経路。

    本番は Supabase RPC `claim_buzz` を推奨 (spec 4-1)。この経路も同じ
    意味論: ラウンド行ロックで直列化し、順位はサーバ側で確定する。
    """

    def post(self, request, round_id):
        with transaction.atomic():
            round_ = get_object_or_404(
                BattleRound.objects.select_for_update(), pk=round_id
            )
            require_participant(round_.room, request.user)
            if round_.revealed_at is None or round_.closed_at is not None:
                raise exceptions.ValidationError("このラウンドは受付中ではありません。")
            existing = round_.buzzes.filter(profile=request.user).first()
            if existing:
                return Response({"rank": existing.rank})
            rank = round_.buzzes.count() + 1
            buzz = BattleBuzz.objects.create(round=round_, profile=request.user, rank=rank)
        return Response({"rank": buzz.rank}, status=201)


class AnswerView(APIView):
    """回答権の検証 → 採点 → スコア加算 (spec 4-2)."""

    def post(self, request, round_id):
        selected = request.data.get("selected_choice_key")
        if not selected:
            raise exceptions.ValidationError("selected_choice_key は必須です。")

        with transaction.atomic():
            round_ = get_object_or_404(
                BattleRound.objects.select_for_update().select_related("question", "room"),
                pk=round_id,
            )
            participant = require_participant(round_.room, request.user)
            if round_.closed_at is not None:
                raise exceptions.ValidationError("このラウンドは終了しています。")

            buzzes = list(round_.buzzes.order_by("rank"))
            my_buzz = next((b for b in buzzes if b.profile_id == request.user.id), None)
            if my_buzz is None:
                raise exceptions.PermissionDenied("早押ししていません。")
            if my_buzz.is_correct is not None:
                raise exceptions.ValidationError("すでに回答済みです。")
            answering = next((b for b in buzzes if b.is_correct is None), None)
            if answering is None or answering.profile_id != request.user.id:
                raise exceptions.PermissionDenied("回答権がありません（誤答順に移ります）。")

            question = round_.question
            is_correct = selected == question.correct_choice_key
            my_buzz.selected_choice_key = selected
            my_buzz.is_correct = is_correct
            my_buzz.save(update_fields=["selected_choice_key", "is_correct"])

            apply_score(participant, correct=is_correct, rank=my_buzz.rank)

            # 対戦の解答も履歴に記録する（ランキング集計からは context で除外,
            # spec 4-2）。習熟度の自動分類はソロと同じルール。
            elapsed_ms = int((timezone.now() - round_.revealed_at).total_seconds() * 1000)
            auto_mastery = (
                AnswerHistory.MasteryLevel.CIRCLE
                if is_correct
                else AnswerHistory.MasteryLevel.CROSS
            )
            AnswerHistory.objects.create(
                user=request.user,
                question=question,
                mastery_level=auto_mastery,
                correct=is_correct,
                response_time_ms=max(elapsed_ms, 0),
                context=AnswerHistory.Context.BATTLE,
            )
            update_review_schedule(request.user, question, auto_mastery)

            if is_correct:
                close_round_and_advance(round_)
            else:
                remaining = [
                    b for b in buzzes if b.is_correct is None and b.pk != my_buzz.pk
                ]
                all_buzzed = round_.room.participants.count() == len(buzzes)
                if not remaining and all_buzzed:
                    close_round_and_advance(round_)

        return Response(
            {
                "correct": is_correct,
                "correct_choice_key": question.correct_choice_key if is_correct else None,
                "score": participant.score,
            }
        )


class RoomResultView(APIView):
    def get(self, request, code):
        room = get_room(code)
        require_participant(room, request.user)
        standings = []
        for p in room.participants.select_related("user").order_by("-score", "id"):
            correct_count = BattleBuzz.objects.filter(
                round__room=room, profile=p.user, is_correct=True
            ).count()
            standings.append(
                {
                    "display_name": p.user.display_name or "匿名ユーザー",
                    "score": p.score,
                    "correct_count": correct_count,
                    "is_me": p.user_id == request.user.id,
                    "is_ai": p.user.is_ai,
                    "left": p.left_at is not None,
                    "points_delta": p.points_delta,
                }
            )
        for i, row in enumerate(standings):
            row["rank"] = (
                i + 1
                if i == 0 or standings[i - 1]["score"] != row["score"]
                else standings[i - 1]["rank"]
            )
        my_points = None
        my_tier = None
        if not request.user.is_ai:
            my_points = request.user.points
            my_tier = compute_tier(request.user)
        return Response(
            {
                "status": room.status,
                "standings": standings,
                "my_points": my_points,
                "my_tier": my_tier,
            }
        )


def ticket_payload(ticket, request_user):
    data = {
        "ticket_id": ticket.id,
        "status": ticket.status,
        "room_code": ticket.room.room_code if ticket.room else None,
        "elapsed_seconds": int((timezone.now() - ticket.created_at).total_seconds()),
        "me": {
            "display_name": request_user.display_name or "匿名ユーザー",
            "university": request_user.university.name if request_user.university else None,
            "tier": compute_tier(request_user),
        },
        "opponent": None,
    }
    if ticket.status in (MatchmakingTicket.Status.MATCHED, MatchmakingTicket.Status.AI_MATCHED):
        data["opponent"] = opponent_profile_payload(ticket)
    return data


class QuickMatchCreateView(APIView):
    """POST /api/battle/quickmatch/ — 対戦のクイックマッチ（同ランク優先）に
    参加する。既に他の待機者がいれば即座にマッチし、いなければ待機列に入る
    （60秒経ってもマッチしなければ GET 側でAI対戦にフォールバックする）。"""

    def post(self, request):
        question_count = int(request.data.get("question_count", 10))
        if question_count not in (5, 10, 20):
            raise exceptions.ValidationError("question_count は 5 / 10 / 20 のみ")
        ticket = create_ticket(request.user, question_count)
        ticket = try_match(ticket)
        return Response(ticket_payload(ticket, request.user), status=201)


class QuickMatchPollView(APIView):
    """GET /api/battle/quickmatch/{id}/ — 探索状況をポーリングする。
    まだ待機中なら再探索し、作成から1分経っていればAI対戦を確定させる。"""

    def get(self, request, ticket_id):
        ticket = get_object_or_404(MatchmakingTicket, pk=ticket_id, user=request.user)
        if ticket.status == MatchmakingTicket.Status.WAITING:
            ticket = try_match(ticket)
        if ticket.status == MatchmakingTicket.Status.WAITING:
            ticket = escalate_to_ai_if_timed_out(ticket)
        return Response(ticket_payload(ticket, request.user))
