"""対戦のAI対戦相手 (spec: クイックマッチで相手が見つからなければAI対戦へ
フォールバック。対戦相手のランクに応じた頭脳のAIとマッチさせる。加えて、
対戦中に相手が離脱・無応答になった場合も同じランク帯のAIに自動で
入れ替わる)。

AI と分からないよう、毎回ランダムな日本人名っぽい表示名と、実在の大学
一覧からランダムに選んだ所属大学を持つ「使い捨ての」Profile
（is_ai=True）をその都度作る。固定の "AI（Bランク）" のような1体を
使い回す旧方式は、同じ偽名が複数の対戦相手の前に繰り返し現れて
見破られる要因になるためやめた。

実際の解答は request を投げてこないため、他の参加者が
GET /battle/rooms/{code}/state/ をポーリングするたびに `simulate_ai_turn`
がそのポーリング時刻を基準にAIの解答を進める。
"""

import random
import uuid

from django.utils import timezone

from accounts.models import Profile, University
from battle.models import BattleBuzz
from battle.scoring import round_time_limit_seconds
from quiz.models import AnswerHistory

# 対戦ランクごとのAIの強さ。
#   accuracy      … 正答率
#   think_seconds … 問題を読み終えてから答えるまでの思考時間
#   chars_per_sec … 読む速さ（強いAIほど速く読む）
#   sd_seconds    … ばらつき
# 人間は問題文を読む時間が要るので、合計の待ち時間は
#   「問題文の長さ ÷ 読む速さ」＋「思考時間」＋ ばらつき
# で決める。短い問題でも最低 MIN_ANSWER_SECONDS は待つ。
AI_TIER_PROFILE = {
    "SS": {"accuracy": 0.95, "think_seconds": 2.0, "chars_per_sec": 20.0, "sd_seconds": 0.8},
    "S": {"accuracy": 0.88, "think_seconds": 2.6, "chars_per_sec": 17.0, "sd_seconds": 1.0},
    "A": {"accuracy": 0.80, "think_seconds": 3.2, "chars_per_sec": 14.0, "sd_seconds": 1.2},
    "B": {"accuracy": 0.72, "think_seconds": 3.8, "chars_per_sec": 12.0, "sd_seconds": 1.4},
    "C": {"accuracy": 0.63, "think_seconds": 4.4, "chars_per_sec": 10.0, "sd_seconds": 1.6},
    "D": {"accuracy": 0.55, "think_seconds": 5.0, "chars_per_sec": 8.5, "sd_seconds": 1.8},
}

# 一瞬で答えると明らかに不自然なので、どんなに短い問題でもこれだけは待つ。
MIN_ANSWER_SECONDS = 3.5
# 相手が先に答えたら、遅くともこの秒数以内には答える（待たされ続けない）。
ANSWER_AFTER_OPPONENT_SECONDS = 2.0
DEFAULT_AI_TIER = "B"  # 未ランクの相手と対戦する場合の既定の強さ

# 表示名の候補。フルネーム風とニックネーム風を混ぜて、いかにも「AI」という
# 雰囲気を出さないようにする（実在の人物を指さない一般的な組み合わせ）。
_SURNAMES = [
    "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
    "吉田", "山田", "佐々木", "松本", "井上", "木村", "林", "斎藤", "清水", "森",
]
_GIVEN_NAMES = [
    "陽翔", "蓮", "湊", "樹", "颯太", "陸", "大和", "悠真", "結菜", "陽菜",
    "凛", "咲良", "美咲", "葵", "さくら", "楓", "杏", "澪", "遥", "光",
]
_NICKNAMES = [
    "ゆうた", "けんと", "みさき", "しょうた", "りく", "あおい", "はると",
    "みくる", "そら", "つばさ", "ののか", "ゆい", "かい", "あかり",
]


def _random_display_name():
    if random.random() < 0.3:
        return random.choice(_NICKNAMES)
    return f"{random.choice(_SURNAMES)} {random.choice(_GIVEN_NAMES)}"


def _random_university():
    # order_by("?") はテーブルが大きいと重いが、大学マスタは高々百件程度。
    return University.objects.order_by("?").first()


def create_disguised_ai_profile(tier):
    """毎回ランダムな人格を持つ使い捨てのAIプロフィールを作る。

    is_ai=True 自体はサーバ内部の判定にのみ使い（ポイント集計対象外にする
    等）、対戦相手に見える情報（表示名・所属大学）からは AI と分からない。
    """
    tier = tier if tier in AI_TIER_PROFILE else DEFAULT_AI_TIER
    profile = Profile.objects.create(
        id=uuid.uuid4(),
        display_name=_random_display_name(),
        university=_random_university(),
        grade=random.randint(3, 6),
        is_ai=True,
    )
    return profile, tier


def _ai_participants(room):
    return list(
        room.participants.select_related("user")
        .filter(user__is_ai=True, left_at__isnull=True)
    )


def _question_length(question):
    """AIが「読む」文字数。問題文・症例文・選択肢をすべて含める。"""
    parts = [question.question_text or "", getattr(question, "case_stem", "") or ""]
    parts += [c.get("text", "") for c in (question.choices or [])]
    return sum(len(p) for p in parts)


def _ai_target_delay(tier, question, *, seed_key):
    """このラウンドでAIが回答するまでの秒数。

    問題文が長いほど遅くなる（人間が読む時間に相当）。ばらつきは
    ``seed_key``（ラウンドとAIの組）で決定的に決める。ポーリングのたびに
    引き直すと、たまたま小さい値が出た瞬間に answer してしまい、実際には
    狙った時間よりずっと早く答えることになるため。
    """
    profile = AI_TIER_PROFILE.get(tier, AI_TIER_PROFILE[DEFAULT_AI_TIER])
    read_seconds = _question_length(question) / profile["chars_per_sec"]
    # Random() の seed はタプルを受け付けないので文字列にして渡す。
    jitter = random.Random(str(seed_key)).gauss(0, profile["sd_seconds"])
    delay = read_seconds + profile["think_seconds"] + jitter
    # 制限時間ぎりぎりに間に合うよう、2秒手前を上限にする。
    latest = round_time_limit_seconds(question) - 2
    return max(MIN_ANSWER_SECONDS, min(latest, delay))


def _simulate_one(room, ai_participant):
    """AIの回答を1手だけ進める。早押しは廃止したので、ランク帯に応じた
    「考える時間」が過ぎたら選択肢を1つ選んで回答する。"""
    round_ = (
        room.rounds.filter(closed_at__isnull=True)
        .select_related("question")
        .order_by("round_number")
        .first()
    )
    if round_ is None or round_.revealed_at is None:
        return
    if round_.buzzes.filter(profile=ai_participant.user).exists():
        return  # 回答済み

    now = timezone.now()
    elapsed = (now - round_.revealed_at).total_seconds()
    profile_tier = ai_participant.ai_tier or DEFAULT_AI_TIER
    target = _ai_target_delay(
        profile_tier,
        round_.question,
        seed_key=(round_.id, str(ai_participant.user_id)),
    )

    # 相手が先に答えていたら、その2秒後までには必ず答える。放っておくと
    # 「相手はもう答えたのにいつまでも待たされる」形になり、テンポが悪い。
    first_other = (
        round_.buzzes.exclude(profile=ai_participant.user)
        .order_by("buzzed_at")
        .values_list("buzzed_at", flat=True)
        .first()
    )
    if first_other is not None:
        answered_at = (first_other - round_.revealed_at).total_seconds()
        target = min(target, answered_at + ANSWER_AFTER_OPPONENT_SECONDS)

    if elapsed < target:
        return  # まだ「考え中」

    from battle.scoring import apply_score
    from battle.views import enforce_round_progress

    accuracy = AI_TIER_PROFILE.get(profile_tier, AI_TIER_PROFILE[DEFAULT_AI_TIER])["accuracy"]
    is_correct = random.random() < accuracy
    question = round_.question
    selected = (
        question.correct_choice_key
        if is_correct
        else next(
            (c["key"] for c in question.choices if c["key"] != question.correct_choice_key),
            question.correct_choice_key,
        )
    )
    BattleBuzz.objects.create(
        round=round_,
        profile=ai_participant.user,
        rank=round_.buzzes.count() + 1,
        selected_choice_key=selected,
        is_correct=is_correct,
    )
    apply_score(ai_participant, correct=is_correct, rank=1)

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

    enforce_round_progress(room)


def simulate_ai_turn(room):
    """このルームにAI参加者がいれば、現在の開講中ラウンドでそれぞれのAIの
    解答を（ポーリング時刻を基準に）1手だけ進める。人間側の state
    ポーリングのたびに呼ばれるので、複数手が一気に進むことはない。

    離脱した参加者の代役として複数のAIが同室にいる場合もあるため、
    対象のAI参加者それぞれについて処理する。"""
    for ai_participant in _ai_participants(room):
        _simulate_one(room, ai_participant)
