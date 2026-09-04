"""対戦モード（HP制バトル）API (spec フェーズ4).

進行:
1. ホストがルーム作成 → 6桁コードを共有 → 参加 → ホストが開始
   （クイックマッチなら同ランク帯の相手と自動で開始）
2. start 時に全 BattleRound を先に作成し、ラウンド1の revealed_at を設定
3. 出題配信は Supabase Realtime（battle_battleround の変更購読）。
   Realtime なし環境向けに GET .../state/ のポーリングでも完全に動く
4. 早押しは廃止。各自が選択肢を選んで POST /rounds/{id}/answer/ を送ると
   その人の解答が確定する（1ラウンド1回のみ。時刻はサーバ側で記録する）
5. 全員の解答がそろうか制限時間切れでラウンドを判定し、HPを削る:
   片方だけ正解 → 不正解側に20% / 両方正解 → 遅い側に10% / 両方不正解 → なし
   どちらかのHPが0になるか全問終わった時点で対戦終了
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

from accounts.ranktier import (
    LEAVE_PENALTY_POINTS,
    apply_points_delta,
    compute_tier,
    progress_for_points,
    rank_state,
    tier_for_points,
)
from accounts.ranktier import (
    battle_points_delta as rank_points_delta,
)
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
    BATTLE_QUESTION_COUNT,
    PARTICIPANT_TIMEOUT_SECONDS,
    apply_score,
    resolve_round_damage,
    round_time_limit_seconds,
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
    """ルーム終了時に一度だけランクポイントを確定する。

    増減は「自分のHP」と「相手のHP」の点差で決まる（accounts.ranktier）。
    大差で勝つほど大きく上がり、大差で負けるほど大きく下がる。
    AI 参加者（accounts.Profile.is_ai）は対象外。
    """
    participants = list(
        room.participants.select_related("user").order_by("-hp", "-score", "id")
    )
    for participant in participants:
        if participant.user.is_ai:
            continue
        # 相手が複数いる場合は最も強かった相手（最高HP）を基準にする。
        others = [p for p in participants if p.pk != participant.pk]
        if not others:
            continue
        opponent_hp = max(p.hp for p in others)
        profile = participant.user
        delta = rank_points_delta(
            my_hp=participant.hp,
            opponent_hp=opponent_hp,
            current_points=profile.points,
        )
        participant.points_delta = delta
        participant.save(update_fields=["points_delta"])
        apply_points_delta(profile, delta)


def resolve_and_close_round(round_):
    """ラウンドを判定してHPを削り、次ラウンドへ進む or 対戦を終了する。

    ダメージ規則 (spec):
    - 片方だけ正解 → 不正解側に20%
    - 両方正解 → 遅く正解した側に10%
    - 両方不正解 → ダメージなし
    """
    room = round_.room
    participants = list(
        room.participants.select_related("user").filter(left_at__isnull=True)
    )
    answers_by_profile = {
        b.profile_id: b for b in round_.buzzes.all()
    }
    answers = [
        (
            p,
            bool(answers_by_profile.get(p.user_id) and answers_by_profile[p.user_id].is_correct),
            answers_by_profile[p.user_id].buzzed_at if p.user_id in answers_by_profile else None,
        )
        for p in participants
    ]
    damage, reason = resolve_round_damage(answers)

    by_id = {p.id: p for p in participants}
    for participant_id, dmg in damage.items():
        participant = by_id[participant_id]
        participant.hp = max(0, participant.hp - dmg)
        participant.save(update_fields=["hp"])

    now = timezone.now()
    round_.closed_at = now
    round_.outcome = {
        # 演出（被弾した側の画面を赤くする）に使うので profile_id で引けるようにする。
        "damage": {str(by_id[pid].user_id): dmg for pid, dmg in damage.items()},
        "reason": reason,
    }
    round_.save(update_fields=["closed_at", "outcome"])

    knocked_out = any(p.hp <= 0 for p in participants)
    next_round = (
        room.rounds.filter(closed_at__isnull=True).order_by("round_number").first()
    )
    if next_round and not knocked_out:
        next_round.revealed_at = now
        next_round.save(update_fields=["revealed_at"])
        return

    # HPが尽きた or 全問終了 → 残りのラウンドを閉じて対戦終了。
    room.rounds.filter(closed_at__isnull=True).update(closed_at=now)
    room.status = BattleRoom.Status.FINISHED
    room.save(update_fields=["status"])
    finalize_room_points(room)


# 旧名（AI シミュレータなど既存の呼び出し元との互換のため）。
close_round_and_advance = resolve_and_close_round


def enforce_round_progress(room):
    """全員が回答済み、または制限時間切れになったラウンドを判定する。

    早押しの概念は廃止し、各自が選択肢を選んで「回答する」を押した時点で
    その人の解答が確定する。両者そろうか時間切れでラウンドを閉じる。"""
    round_ = open_round(room)
    if round_ is None or round_.revealed_at is None:
        return
    now = timezone.now()
    deadline = round_.revealed_at + datetime.timedelta(
        seconds=round_time_limit_seconds(round_.question)
    )
    if now >= deadline:
        resolve_and_close_round(round_)
        return
    active_ids = set(
        room.participants.filter(left_at__isnull=True).values_list("user_id", flat=True)
    )
    if not active_ids:
        return
    answered_ids = set(
        round_.buzzes.filter(is_correct__isnull=False).values_list("profile_id", flat=True)
    )
    if active_ids <= answered_ids:
        resolve_and_close_round(round_)


def _replace_with_ai(room, participant):
    """参加者1人をHPを凍結して退場させ、同じランク帯のAI（偽名・偽の
    所属大学つきで、人間には見分けが付かない）を即座に代役として入れる。

    離脱にはランクポイントのペナルティを課す。自分から退出した場合だけで
    なく無応答での自動退場にも課すのは、そうしないとタブを閉じるだけで
    ペナルティを回避できてしまうため。
    """
    if participant.left_at is not None:
        return
    tier = compute_tier(participant.user) or DEFAULT_AI_TIER
    participant.left_at = timezone.now()
    participant.save(update_fields=["left_at"])

    profile = participant.user
    if not profile.is_ai:
        # ranked_matches は増やさない（対戦を1回こなしたわけではないため）。
        # 対戦終了時の勝敗ぶんの増減は finalize_room_points が別途行う。
        profile.points = max(0, profile.points - LEAVE_PENALTY_POINTS)
        profile.save(update_fields=["points"])

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
        # 問題数の選択は廃止（対戦形式は一律で同じ）。既存クライアントが
        # question_count を送ってきても無視する。
        question_count = BATTLE_QUESTION_COUNT
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
    ホストを引き継ぎ、誰もいなくなったらルームごと削除する。ペナルティは無い。
    対戦中: HPを凍結して退場し、同じランク帯のAIが即座に代役として入る
    （他の参加者が対戦を続けられるように）。離脱ペナルティとしてランク
    ポイントを LEAVE_PENALTY_POINTS 引く。人間が誰もいなくなったら
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
                "profile_id": str(p.user_id),
                "display_name": p.user.display_name or "匿名ユーザー",
                "university": p.user.university.name if p.user.university else None,
                # AI の代役はマッチ時のランク帯をそのまま見せる（見分けが付かない
                # ようにするため、AIかどうかはクライアントに返さない）。
                "tier": p.ai_tier or compute_tier(p.user),
                "score": p.score,
                "hp": p.hp,
                "is_me": p.user_id == request.user.id,
                "is_host": p.user_id == room.host_id,
                "connected": p.left_at is None and p.last_seen_at >= cutoff,
                "left": p.left_at is not None,
            }
            for p in room.participants.select_related(
                "user", "user__university"
            ).order_by("id")
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
            answers = list(round_.buzzes.select_related("profile").order_by("rank"))
            my_answer = next(
                (b for b in answers if b.profile_id == request.user.id), None
            )
            payload["round"] = {
                "id": round_.id,
                "number": round_.round_number,
                "total": room.question_count,
                "revealed_at": round_.revealed_at,
                "closes_at": round_.revealed_at
                + datetime.timedelta(
                    seconds=round_time_limit_seconds(round_.question)
                ),
                "question": QuestionSerializer(round_.question).data,
                # 誰がもう答えたかだけ見せる（何を選んだかは決着まで伏せる）。
                "answered_profile_ids": [str(b.profile_id) for b in answers],
                "i_have_answered": my_answer is not None,
                "my_selected_choice_key": (
                    my_answer.selected_choice_key if my_answer else None
                ),
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
                .order_by("buzzed_at")
                .first()
            )
            outcome = last_closed.outcome or {}
            payload["last_result"] = {
                "number": last_closed.round_number,
                "correct_choice_key": last_closed.question.correct_choice_key,
                "explanation": last_closed.question.explanation,
                "winner": (winner.profile.display_name or "匿名ユーザー") if winner else None,
                # 攻撃演出用: {profile_id: 受けたダメージ%} と決着理由。
                "damage": outcome.get("damage", {}),
                "reason": outcome.get("reason"),
                "my_damage": (outcome.get("damage") or {}).get(str(request.user.id), 0),
            }

        return Response(payload)


class AnswerView(APIView):
    """選択肢を選んで回答する (spec: 早押しボタンは廃止)。

    各参加者は1ラウンドにつき1回だけ回答できる。回答の速さは
    ``BattleBuzz.buzzed_at`` に記録され、両者正解時にどちらが遅かったかの
    判定に使う。ラウンドの決着（HPの増減）は全員の回答がそろった時点、
    または制限時間切れで ``resolve_and_close_round`` が行う。
    """

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
            if participant.left_at is not None:
                raise exceptions.PermissionDenied("この対戦からは離脱済みです。")
            if round_.revealed_at is None or round_.closed_at is not None:
                raise exceptions.ValidationError("このラウンドは受付中ではありません。")
            if round_.buzzes.filter(profile=request.user).exists():
                raise exceptions.ValidationError("すでに回答済みです。")

            question = round_.question
            if selected not in {c["key"] for c in question.choices}:
                raise exceptions.ValidationError("選択肢が不正です。")

            is_correct = selected == question.correct_choice_key
            rank = round_.buzzes.count() + 1
            BattleBuzz.objects.create(
                round=round_,
                profile=request.user,
                rank=rank,
                selected_choice_key=selected,
                is_correct=is_correct,
            )
            apply_score(participant, correct=is_correct, rank=rank)

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

            enforce_round_progress(round_.room)

        participant.refresh_from_db()
        return Response(
            {
                "correct": is_correct,
                "correct_choice_key": question.correct_choice_key,
                "score": participant.score,
                "hp": participant.hp,
            }
        )


def result_questions(room, profile):
    """対戦で出題された問題の振り返り。

    決着済み（closed_at がある）ラウンドだけを対象に、自分がどう答えたかと
    解説を返す。まだ開いているラウンドを混ぜると、途中終了した対戦で「誰も
    答えていない問題」が振り返りに並んでしまう。無解答（時間切れ）は
    correct=false ではなく answered=false で区別する。解説は対戦が終わって
    から読むものなので、ここで初めて返す。
    """
    rows = []
    rounds = (
        room.rounds.filter(closed_at__isnull=False)
        .select_related("question", "question__question_set")
        .prefetch_related("buzzes")
        .order_by("round_number")
    )
    for round_ in rounds:
        mine = next((b for b in round_.buzzes.all() if b.profile_id == profile.id), None)
        q = round_.question
        rows.append(
            {
                "round_number": round_.round_number,
                "question_id": q.id,
                "category": q.category,
                "exam_type": q.exam_type,
                "case_stem": q.question_set.case_stem if q.question_set_id else None,
                "question_text": q.question_text,
                "choices": q.choices,
                "correct_choice_key": q.correct_choice_key,
                "explanation": q.explanation,
                "answered": mine is not None,
                "selected_choice_key": mine.selected_choice_key if mine else None,
                "correct": bool(mine.is_correct) if mine else False,
            }
        )
    return rows


class RoomResultView(APIView):
    def get(self, request, code):
        room = get_room(code)
        require_participant(room, request.user)
        standings = []
        for p in room.participants.select_related("user", "user__university").order_by("-hp", "-score", "id"):
            correct_count = BattleBuzz.objects.filter(
                round__room=room, profile=p.user, is_correct=True
            ).count()
            standings.append(
                {
                    "display_name": p.user.display_name or "匿名ユーザー",
                    "university": p.user.university.name if p.user.university else None,
                    "hp": p.hp,
                    "score": p.score,
                    "correct_count": correct_count,
                    "is_me": p.user_id == request.user.id,
                    "left": p.left_at is not None,
                    "points_delta": p.points_delta,
                }
            )
        for i, row in enumerate(standings):
            row["rank"] = (
                i + 1
                if i == 0 or (standings[i - 1]["hp"], standings[i - 1]["score"]) != (row["hp"], row["score"])
                else standings[i - 1]["rank"]
            )
        me = next((r for r in standings if r["is_me"]), None)
        my_delta = me["points_delta"] if me else None
        state = rank_state(request.user)
        # 増減バーのアニメーション用に「増減前」の位置も返す。
        before = None
        if my_delta is not None:
            before_points = max(0, request.user.points - my_delta)
            before = {
                "tier": tier_for_points(before_points),
                "progress": progress_for_points(before_points),
                "points": before_points,
            }
        return Response(
            {
                "status": room.status,
                "standings": standings,
                "questions": result_questions(room, request.user),
                "my_points": None if request.user.is_ai else request.user.points,
                "my_tier": None if request.user.is_ai else state["tier"],
                "rank": {
                    "before": before,
                    "after": state,
                    "delta": my_delta,
                    # 昇格/降格したかどうか（演出の出し分けに使う）
                    "promoted": bool(
                        before and state["tier"] and before["tier"] != state["tier"] and my_delta and my_delta > 0
                    ),
                    "demoted": bool(
                        before and state["tier"] and before["tier"] != state["tier"] and my_delta and my_delta < 0
                    ),
                },
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
    （一定時間マッチしなければ GET 側でAI対戦にフォールバックする）。"""

    def post(self, request):
        # 問題数の選択は廃止（対戦形式は一律で同じ）。既存クライアントが
        # question_count を送ってきても無視する。
        question_count = BATTLE_QUESTION_COUNT
        ticket = create_ticket(request.user, question_count)
        ticket = try_match(ticket)
        return Response(ticket_payload(ticket, request.user), status=201)


class QuickMatchPollView(APIView):
    """GET /api/battle/quickmatch/{id}/ — 探索状況をポーリングする。
    まだ待機中なら再探索し、規定の待ち時間を過ぎていればAI対戦を確定させる。"""

    def get(self, request, ticket_id):
        ticket = get_object_or_404(MatchmakingTicket, pk=ticket_id, user=request.user)
        if ticket.status == MatchmakingTicket.Status.WAITING:
            ticket = try_match(ticket)
        if ticket.status == MatchmakingTicket.Status.WAITING:
            ticket = escalate_to_ai_if_timed_out(ticket)
        return Response(ticket_payload(ticket, request.user))
