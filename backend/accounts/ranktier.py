"""対戦＋模試（週次/月次）合算ポイントによるランク階層 (spec: SS/S/A/B/C/D)。

`Profile.points` は対戦の勝敗・週次/月次模試の成績で増減する累計ポイント
（初期値1000）。ランクはその時点の全ランク対象ユーザー内での相対位置
（上位%）で決まるため、値そのものではなく毎回その場で計算する。

ランク対象は `ranked_matches >= 1`（一度もランク付き対戦・模試をした
ことがないユーザーは「未ランク」とし、母集団にも含めない）。
"""

from accounts.models import Profile

# 累計ポイントの初期値（対戦・模試の勝敗で増減する基準点）
STARTING_POINTS = 1000

# 上位 X% 以内なら該当ランク（spec: 5/25/40/60/80/100）
TIER_THRESHOLDS = [
    (0.05, "SS"),
    (0.25, "S"),
    (0.40, "A"),
    (0.60, "B"),
    (0.80, "C"),
    (1.01, "D"),  # 残り全部（浮動小数点誤差対策で1.0よりわずかに大きくする）
]

# 模試（週次/月次のみ）の順位バケットごとの獲得ポイント。対戦と同じ
# 5段階の閾値をそのまま「今回の成績の上位%」に流用する。
EXAM_POINTS_BY_BUCKET = {
    "SS": 50,
    "S": 30,
    "A": 15,
    "B": 5,
    "C": -5,
    "D": -15,
}


def _ranked_queryset():
    return Profile.objects.filter(is_ai=False, ranked_matches__gte=1)


def tier_for_top_fraction(top_fraction):
    """`top_fraction`（0=1位, 1=最下位）から SS〜D のランク名を返す。"""
    for threshold, tier in TIER_THRESHOLDS:
        if top_fraction <= threshold:
            return tier
    return "D"  # pragma: no cover - THRESHOLDS の最後が1.01なので到達しない


def compute_tier(profile):
    """profile の現在のランク（"SS".."D"）。ランク対象外なら None。"""
    if profile.is_ai or profile.ranked_matches < 1:
        return None
    qs = _ranked_queryset()
    total = qs.count()
    if total == 0:
        return None
    # 「自分より厳密に上のポイントを持つ人数」で top% を決める。「以上」で
    # 数えると、母集団が自分1人だけの場合に top_fraction=1.0（最下位=D）
    # という直感に反する結果になってしまう（1位のはずが1人しかいないせいで
    # 最下位判定される）。「より上の人数」なら常に0位=SSからの相対位置になる。
    strictly_better = qs.filter(points__gt=profile.points).count()
    return tier_for_top_fraction(strictly_better / total)


def points_bucket_for_percentile(percentile_top_pct):
    """模試の「上位◯%」（0〜100, 小さいほど好成績）からポイント増減バケット名を返す。"""
    fraction = percentile_top_pct / 100
    return tier_for_top_fraction(fraction)


def exam_points_delta(percentile_top_pct, *, speed_bonus=0):
    """模試（週次/月次）のポイント増減 = 順位バケット基礎点 + 速さボーナス。"""
    bucket = points_bucket_for_percentile(percentile_top_pct)
    return EXAM_POINTS_BY_BUCKET[bucket] + speed_bonus


def speed_bonus(my_avg_response_ms, cohort_avg_response_ms, *, cap=10):
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
