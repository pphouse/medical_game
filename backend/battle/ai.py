"""対戦のAI対戦相手 (spec: クイックマッチで1分間マッチしなければAI対戦へ
フォールバック。相手のランクに応じた頭脳のAIとマッチさせる)。

AI は accounts.Profile（is_ai=True の固定6体、ランクごとに1体）として
振る舞う。実際の早押し・解答は request を投げてこないため、他の参加者が
GET /battle/rooms/{code}/state/ をポーリングするたびに `simulate_ai_turn`
がそのポーリング時刻を基準にAIの行動（早押し・解答）を進める。
"""

import random
import uuid

from django.utils import timezone

from accounts.models import Profile
from battle.models import BattleBuzz, BattleParticipant, BattleRound
from battle.scoring import ROUND_TIME_LIMIT_SECONDS
from quiz.models import AnswerHistory

# 対戦ランクごとのAIの強さ（正答率・平均反応秒・ばらつき秒）
AI_TIER_PROFILE = {
    "SS": {"accuracy": 0.90, "avg_seconds": 1.5, "sd_seconds": 0.5},
    "S": {"accuracy": 0.78, "avg_seconds": 2.5, "sd_seconds": 0.7},
    "A": {"accuracy": 0.65, "avg_seconds": 3.5, "sd_seconds": 0.9},
    "B": {"accuracy": 0.52, "avg_seconds": 4.5, "sd_seconds": 1.0},
    "C": {"accuracy": 0.40, "avg_seconds": 5.5, "sd_seconds": 1.1},
    "D": {"accuracy": 0.30, "avg_seconds": 6.5, "sd_seconds": 1.2},
}
DEFAULT_AI_TIER = "B"  # 未ランクのユーザーと対戦する場合の既定の強さ

# 固定UUID（tierごとに1体だけ存在させる, uuid5で決定的に生成）
_AI_NAMESPACE = uuid.UUID("6b6f2f8e-9c2b-4f2a-9a8e-4e5b7d6c1a10")


def ai_profile_id(tier):
    return uuid.uuid5(_AI_NAMESPACE, f"battle-ai-{tier}")


def get_or_create_ai_profile(tier):
    tier = tier if tier in AI_TIER_PROFILE else DEFAULT_AI_TIER
    profile, _ = Profile.objects.get_or_create(
        id=ai_profile_id(tier),
        defaults={"display_name": f"AI（{tier}ランク）", "is_ai": True},
    )
    if not profile.is_ai:  # 万一IDが衝突しても人間のプロフィールは壊さない
        profile.is_ai = True
        profile.display_name = profile.display_name or f"AI（{tier}ランク）"
        profile.save(update_fields=["is_ai", "display_name"])
    return profile


def _ai_participant(room):
    return room.participants.select_related("user").filter(user__is_ai=True).first()


def _ai_target_delay(tier):
    profile = AI_TIER_PROFILE.get(tier, AI_TIER_PROFILE[DEFAULT_AI_TIER])
    delay = random.gauss(profile["avg_seconds"], profile["sd_seconds"])
    return max(0.3, min(ROUND_TIME_LIMIT_SECONDS - 1, delay))


def simulate_ai_turn(room):
    """このルームにAI参加者がいれば、現在の開講中ラウンドでAIの早押し・
    解答を（ポーリング時刻を基準に）1手だけ進める。人間側の state ポーリング
    のたびに呼ばれるので、複数手が一気に進むことはない。"""
    ai_participant = _ai_participant(room)
    if ai_participant is None:
        return

    round_ = (
        room.rounds.filter(closed_at__isnull=True)
        .select_related("question")
        .order_by("round_number")
        .first()
    )
    if round_ is None or round_.revealed_at is None:
        return

    now = timezone.now()
    elapsed = (now - round_.revealed_at).total_seconds()
    profile_tier = next(
        (t for t in AI_TIER_PROFILE if ai_participant.user.id == ai_profile_id(t)),
        DEFAULT_AI_TIER,
    )

    my_buzz = round_.buzzes.filter(profile=ai_participant.user).first()
    if my_buzz is None:
        target_delay = _ai_target_delay(profile_tier)
        if elapsed < target_delay:
            return  # まだ「考え中」
        rank = round_.buzzes.count() + 1
        BattleBuzz.objects.create(round=round_, profile=ai_participant.user, rank=rank)
        return  # 早押しした手番はここまで（解答は次のポーリングで判定する）

    if my_buzz.is_correct is not None:
        return  # 解答済み

    buzzes = list(round_.buzzes.order_by("rank"))
    answering = next((b for b in buzzes if b.is_correct is None), None)
    if answering is None or answering.pk != my_buzz.pk:
        return  # まだAIの回答権の順番ではない

    from battle.scoring import apply_score
    from battle.views import close_round_and_advance

    accuracy = AI_TIER_PROFILE.get(profile_tier, AI_TIER_PROFILE[DEFAULT_AI_TIER])["accuracy"]
    is_correct = random.random() < accuracy
    question = round_.question
    my_buzz.selected_choice_key = (
        question.correct_choice_key if is_correct else next(
            (c["key"] for c in question.choices if c["key"] != question.correct_choice_key),
            question.correct_choice_key,
        )
    )
    my_buzz.is_correct = is_correct
    my_buzz.save(update_fields=["selected_choice_key", "is_correct"])
    apply_score(ai_participant, correct=is_correct, rank=my_buzz.rank)

    AnswerHistory.objects.create(
        user=ai_participant.user,
        question=question,
        mastery_level=(
            AnswerHistory.MasteryLevel.CIRCLE if is_correct else AnswerHistory.MasteryLevel.CROSS
        ),
        correct=is_correct,
        response_time_ms=int(elapsed * 1000),
        context=AnswerHistory.Context.BATTLE,
    )

    if is_correct:
        close_round_and_advance(round_)
    else:
        remaining = [b for b in buzzes if b.is_correct is None and b.pk != my_buzz.pk]
        all_buzzed = round_.room.participants.count() == len(buzzes)
        if not remaining and all_buzzed:
            close_round_and_advance(round_)
