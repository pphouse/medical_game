"""対戦の得点定数 (spec 4-2)."""

CORRECT_POINTS = 100
FIRST_BUZZ_BONUS = 20
WRONG_PENALTY = 30

# 出題からこの秒数で強制クローズ（誰も正解できなかった場合）
ROUND_TIME_LIMIT_SECONDS = 30

# --- HP制バトル (spec: お互い100%から始まり、攻撃でHPを削り合う) ----------
# 全対戦で共通の問題数（問題数の選択は廃止し、一律同じ対戦形式にする）。
BATTLE_QUESTION_COUNT = 10
STARTING_HP = 100
# 片方だけ正解 → 不正解側に20%
DAMAGE_WRONG = 20
# 両方正解 → 遅く正解した側に10%
DAMAGE_SLOWER = 10
# この秒数応答がない参加者は切断とみなす (spec 4-2)
PARTICIPANT_TIMEOUT_SECONDS = 30


def score_delta(*, correct, rank):
    """正解 +100（そのラウンドで最初に解答していれば +20）、誤答 −30。"""
    if correct:
        return CORRECT_POINTS + (FIRST_BUZZ_BONUS if rank == 1 else 0)
    return -WRONG_PENALTY


def apply_score(participant, *, correct, rank):
    participant.score = max(0, participant.score + score_delta(correct=correct, rank=rank))
    participant.save(update_fields=["score"])


# 対戦ランクポイント（累計ポイント, spec: 対戦＋模試の合算でSS〜Dランク）。
# ルーム内の最終順位に応じて滑らかに配点する: 1位 +25 〜 最下位 -15。
BATTLE_POINTS_BEST = 25
BATTLE_POINTS_WORST = -15


def battle_points_delta(rank, participant_count):
    """ルーム内順位 (1始まり) から対戦ランクポイントの増減を返す。"""
    if participant_count <= 1:
        return 0
    normalized = (rank - 1) / (participant_count - 1)  # 0=1位 .. 1=最下位
    span = BATTLE_POINTS_BEST - BATTLE_POINTS_WORST
    return round(BATTLE_POINTS_BEST - span * normalized)


def resolve_round_damage(answers):
    """1ラウンドの解答結果からダメージを決める。

    ``answers`` は [(participant, is_correct, answered_at), ...]。
    - 片方だけ正解 → 不正解側に DAMAGE_WRONG
    - 両方正解 → 遅く正解した側に DAMAGE_SLOWER
    - 両方不正解 / 全員無回答 → ダメージなし
    未回答（answered_at が None）は不正解として扱う。

    返り値は {participant_id: 受けたダメージ} と決着理由の文字列。
    """
    if len(answers) < 2:
        return {}, "no_contest"

    correct = [a for a in answers if a[1]]
    wrong = [a for a in answers if not a[1]]

    if correct and wrong:
        return {p.id: DAMAGE_WRONG for p, _, _ in wrong}, "wrong_answer"

    if len(correct) == len(answers):
        # 全員正解: いちばん遅かった人だけが被弾する。
        answered = [a for a in correct if a[2] is not None]
        if len(answered) < 2:
            return {}, "draw"
        slowest = max(answered, key=lambda a: a[2])
        return {slowest[0].id: DAMAGE_SLOWER}, "slower_answer"

    return {}, "all_wrong"
