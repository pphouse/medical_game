"""対戦＋模試（週次/月次）で増減するランク (D→C→B→A→S→SS)。

`Profile.points` は累計のランクポイント（0スタート）。ランクは他人との
相対位置ではなく、この累計値だけで決まる絶対ラダー方式:

    0-99 = D / 100-199 = C / 200-299 = B / 300-399 = A / 400-499 = S / 500- = SS

各ランクの中では 0〜99% の進捗を持ち、100% を超えると次のランクへ上がって
0% から再スタートする。負けるとポイントが減り、0% を下回ると一つ下の
ランクへ落ちる（D の 0% が下限）。

増減幅は「HPの点差」で変わり、上のランクほど1勝で伸びにくくしてある
（TIER_GAIN_MULTIPLIER）。想定勝率7割・平均点差50%のプレイヤーで、
D から SS まで概ね120戦前後かかる設計。
"""

from accounts.models import Profile

# ランクの並び（下から上へ）と、1ランクぶんのポイント幅
RANK_TIERS = ["D", "C", "B", "A", "S", "SS"]
POINTS_PER_TIER = 100
MAX_TIER_INDEX = len(RANK_TIERS) - 1

# 累計ポイントの初期値（全員ここから始まる = D の 0%）
STARTING_POINTS = 0

# 上のランクほど1勝で伸びにくくする（勝ち幅にのみ効かせる。負け幅は据え置きで、
# 上位ほど「上がりにくく落ちやすい」= 上位ランクの価値を保つ）。
TIER_GAIN_MULTIPLIER = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]

# 勝敗の基礎点と、HPの点差(0〜100)による上乗せ分。
WIN_BASE_POINTS = 8
WIN_MARGIN_POINTS = 10  # 点差100%で +10 → 勝ちは +8〜+18（ランク補正前）
LOSS_BASE_POINTS = 6
LOSS_MARGIN_POINTS = 6  # 大差で負けるほど痛い → -6〜-12

# 模試（週次/月次のみ）の順位バケットごとの増減。対戦1戦（+8〜+18）と
# 釣り合う大きさに揃えてある。
EXAM_POINTS_BY_BUCKET = {
    "SS": 20,
    "S": 12,
    "A": 6,
    "B": 2,
    "C": -2,
    "D": -6,
}

# 模試の「上位◯%」から増減バケットを引くための閾値（spec: 5/25/40/60/80/100）。
TIER_THRESHOLDS = [
    (0.05, "SS"),
    (0.25, "S"),
    (0.40, "A"),
    (0.60, "B"),
    (0.80, "C"),
    (1.01, "D"),  # 残り全部（浮動小数点誤差対策で1.0よりわずかに大きくする）
]


def tier_index_for_points(points):
    return min(max(int(points), 0) // POINTS_PER_TIER, MAX_TIER_INDEX)


def tier_for_points(points):
    return RANK_TIERS[tier_index_for_points(points)]


def progress_for_points(points):
    """そのランクの中での進捗% (0〜100)。最上位ランクは常に100%。"""
    points = max(int(points), 0)
    if tier_index_for_points(points) >= MAX_TIER_INDEX:
        return 100
    return points % POINTS_PER_TIER


def rank_state(profile):
    """表示用のランク情報。未ランク（1戦もしていない）なら tier は None。"""
    if profile.is_ai or profile.ranked_matches < 1:
        return {
            "tier": None,
            "progress": 0,
            "points": profile.points,
            "next_tier": RANK_TIERS[0],
        }
    index = tier_index_for_points(profile.points)
    return {
        "tier": RANK_TIERS[index],
        "progress": progress_for_points(profile.points),
        "points": profile.points,
        "next_tier": RANK_TIERS[index + 1] if index < MAX_TIER_INDEX else None,
    }


def compute_tier(profile):
    """profile の現在のランク（"D".."SS"）。ランク対象外なら None。"""
    if profile.is_ai or profile.ranked_matches < 1:
        return None
    return tier_for_points(profile.points)


def battle_points_delta(*, my_hp, opponent_hp, current_points):
    """対戦1戦のランクポイント増減。

    HPの点差が大きいほど動きが大きい。引き分け（同HP）は増減なし。
    """
    margin = min(100, abs(int(my_hp) - int(opponent_hp))) / 100
    if my_hp == opponent_hp:
        return 0
    if my_hp > opponent_hp:
        multiplier = TIER_GAIN_MULTIPLIER[tier_index_for_points(current_points)]
        return max(1, round((WIN_BASE_POINTS + WIN_MARGIN_POINTS * margin) * multiplier))
    return -round(LOSS_BASE_POINTS + LOSS_MARGIN_POINTS * margin)


def tier_for_top_fraction(top_fraction):
    """`top_fraction`（0=1位, 1=最下位）から SS〜D のバケット名を返す。
    模試の成績バケット判定にのみ使う（ランクそのものは累計ポイントで決まる）。"""
    for threshold, tier in TIER_THRESHOLDS:
        if top_fraction <= threshold:
            return tier
    return "D"  # pragma: no cover - THRESHOLDS の最後が1.01なので到達しない


def points_bucket_for_percentile(percentile_top_pct):
    """模試の「上位◯%」（0〜100, 小さいほど好成績）から増減バケット名を返す。"""
    return tier_for_top_fraction(percentile_top_pct / 100)


def exam_points_delta(percentile_top_pct, *, speed_bonus=0):
    """模試（週次/月次）のポイント増減 = 順位バケット基礎点 + 速さボーナス。"""
    bucket = points_bucket_for_percentile(percentile_top_pct)
    return EXAM_POINTS_BY_BUCKET[bucket] + speed_bonus


def speed_bonus(my_avg_response_ms, cohort_avg_response_ms, *, cap=4):
    """解答速度ボーナス: 母集団平均より速いほど加点、遅いほど減点（±cap）。"""
    if not cohort_avg_response_ms:
        return 0
    ratio = (cohort_avg_response_ms - my_avg_response_ms) / cohort_avg_response_ms
    return max(-cap, min(cap, round(ratio * cap * 2)))


def apply_points_delta(profile, delta):
    """Profile.points に delta を適用し、ranked_matches をインクリメントする。"""
    profile.points = max(0, profile.points + delta)
    profile.ranked_matches += 1
    profile.save(update_fields=["points", "ranked_matches"])
