"""クイックマッチ（対戦のマッチメイキング）。

spec: オンラインの中でも同じレベルの人がマッチしやすいようにする。
1分経ってもマッチしない場合はAI対戦とし、そのユーザーのランクに合わせた
頭脳のAIとマッチさせる。

ポーリング駆動（このアプリは常駐ワーカーを持たないサーバーレス志向,
docs/deploy-vercel.md）: マッチ探索も「もう1分経ったか」の判定も、
クライアントが GET /battle/quickmatch/{id}/ を叩くたびに行う。
"""

import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.ranktier import compute_tier
from battle.ai import get_or_create_ai_profile
from battle.models import BattleParticipant, BattleRoom, MatchmakingTicket

MATCH_TIMEOUT_SECONDS = 60


def _create_room(host, question_count):
    for _ in range(10):
        code = f"{secrets.randbelow(900000) + 100000}"
        try:
            return BattleRoom.objects.create(
                host=host, room_code=code, question_count=question_count
            )
        except IntegrityError:
            continue
    raise RuntimeError("ルームコードの生成に失敗しました。")


def _tier_of(profile):
    return compute_tier(profile) or ""


@transaction.atomic
def create_ticket(user, question_count):
    existing = MatchmakingTicket.objects.filter(
        user=user, status=MatchmakingTicket.Status.WAITING
    ).first()
    if existing:
        return existing
    return MatchmakingTicket.objects.create(
        user=user, question_count=question_count, tier_snapshot=_tier_of(user)
    )


@transaction.atomic
def try_match(ticket):
    """同じ問題数の待機列から相手を探す。同ランク優先、いなければ誰でも。"""
    if ticket.status != MatchmakingTicket.Status.WAITING:
        return ticket

    candidates = (
        MatchmakingTicket.objects.select_for_update()
        .filter(status=MatchmakingTicket.Status.WAITING, question_count=ticket.question_count)
        .exclude(pk=ticket.pk)
        .exclude(user=ticket.user)
        .order_by("created_at")
    )
    same_tier = [c for c in candidates if c.tier_snapshot == ticket.tier_snapshot]
    opponent_ticket = (same_tier or list(candidates))
    opponent_ticket = opponent_ticket[0] if opponent_ticket else None
    if opponent_ticket is None:
        return ticket

    room = _create_room(ticket.user, ticket.question_count)
    BattleParticipant.objects.create(room=room, user=ticket.user)
    BattleParticipant.objects.create(room=room, user=opponent_ticket.user)
    from battle.views import start_room

    start_room(room)

    MatchmakingTicket.objects.filter(pk__in=[ticket.pk, opponent_ticket.pk]).update(
        status=MatchmakingTicket.Status.MATCHED, room=room
    )
    ticket.refresh_from_db()
    return ticket


@transaction.atomic
def escalate_to_ai_if_timed_out(ticket):
    if ticket.status != MatchmakingTicket.Status.WAITING:
        return ticket
    elapsed = (timezone.now() - ticket.created_at).total_seconds()
    if elapsed < MATCH_TIMEOUT_SECONDS:
        return ticket

    ai_tier = ticket.tier_snapshot or "B"
    ai_profile = get_or_create_ai_profile(ai_tier)
    room = _create_room(ticket.user, ticket.question_count)
    BattleParticipant.objects.create(room=room, user=ticket.user)
    BattleParticipant.objects.create(room=room, user=ai_profile)
    from battle.views import start_room

    start_room(room)

    ticket.status = MatchmakingTicket.Status.AI_MATCHED
    ticket.room = room
    ticket.save(update_fields=["status", "room"])
    return ticket


def opponent_profile_payload(ticket):
    """マッチ成立後の「対戦前プロフィール」表示用（ニックネーム・大学・ランク）。"""
    if ticket.room is None:
        return None
    other = ticket.room.participants.select_related("user__university").exclude(
        user=ticket.user
    ).first()
    if other is None:
        return None
    profile = other.user
    return {
        "display_name": profile.display_name or "匿名ユーザー",
        "university": profile.university.name if profile.university else None,
        "tier": compute_tier(profile) if not profile.is_ai else ticket.tier_snapshot or "B",
        "is_ai": profile.is_ai,
    }
