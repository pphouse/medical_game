"""対戦の得点定数 (spec 4-2)."""

CORRECT_POINTS = 100
FIRST_BUZZ_BONUS = 20
WRONG_PENALTY = 30

# 出題からこの秒数で強制クローズ（誰も正解できなかった場合）
ROUND_TIME_LIMIT_SECONDS = 30
# この秒数応答がない参加者は切断とみなす (spec 4-2)
PARTICIPANT_TIMEOUT_SECONDS = 30


def score_delta(*, correct, rank):
    """正解 +100（早押し1位なら +20 ボーナス）、誤答 −30。"""
    if correct:
        return CORRECT_POINTS + (FIRST_BUZZ_BONUS if rank == 1 else 0)
    return -WRONG_PENALTY


def apply_score(participant, *, correct, rank):
    participant.score = max(0, participant.score + score_delta(correct=correct, rank=rank))
    participant.save(update_fields=["score"])
