"""試験ごとの「出題範囲の割合」（出題構成比）。

問題バンクの科目ごとの偏りをならすための基準値。バンクの実測値をそのまま
出題比率に使うと、たまたま問題を多く作った科目が模試でも多く出てしまう
（実測で CBT の 医学総論・公衆衛生・診療の基本 が 1012問中255問＝25%を
占め、模試でも毎回4分の1がそこから出ていた）。そこで「本番の試験でどの
くらい出るか」を独立した表として持ち、

* 問題バンクの目標問題数（quiz/management/commands/question_targets.py）
* 模試の出題抽選（exams/management/commands/create_scheduled_exam.py）

の両方でこの表を基準にする。

値は**相対重み**であり、合計が何になっても構わない（使う側で正規化する）。
絶対問題数を書くと本番の問題数が変わるたびに全行を直すことになるため。

出典と考え方:

医師国家試験（400問構成: 必修100問 + 一般・臨床300問）
    必修問題の比率と、各科の出題数の目安は 114〜119回の実際の構成に
    合わせている。臓器別各論は QB / イヤーノートの章立てに対応させ、
    各章の出題数の相場をそのまま重みにした。

CBT（採点対象320問）
    コアカリの領域構成に対応させる。基礎医学（A〜C領域）約2割、
    臨床医学各論（D領域）約6割、総論・診療の基本（E〜F領域）約1.5割、
    残りが多選択肢・四連問（ブロック5・6の形式枠）。

なお **どの科目にも最低 MIN_QUESTIONS_PER_CATEGORY 問は確保する**のが
先で、この重みは「最低数を配ったあとの上積み」をどう配るかを決める。
比率だけで配ると、出題数の少ない科目（放射線科・免疫膠原病など）に
演習できるだけの問題が用意されない。
"""

from quiz.categories import CBT, CBT_CATEGORIES, KOKUSHI, KOKUSHI_CATEGORIES

# どの科目にも最低これだけは用意する（演習として成立する下限）。
MIN_QUESTIONS_PER_CATEGORY = 15

KOKUSHI_WEIGHTS = {
    # 必修問題は B・E ブロックの100問ぶんで、全体の約4分の1を占める。
    "必修問題": 100,
    "医学総論": 45,
    "公衆衛生": 32,
    # --- 臓器別各論 ---
    "消化管": 22,
    "肝・胆・膵": 16,
    "循環器": 24,
    "代謝・内分泌": 18,
    "腎・泌尿器": 14,
    "免疫・膠原病": 8,
    "血液": 12,
    "感染症": 12,
    "呼吸器": 22,
    "神経": 18,
    # 3科目を統合したので重みも足し合わせる（4+10+4）。
    "救急・中毒・麻酔": 18,
    "小児科": 16,
    "婦人科・乳腺外科": 12,
    "産科": 12,
    "眼科": 8,
    "耳鼻咽喉科": 8,
    "整形外科": 10,
    "精神科": 12,
    "皮膚科": 8,
    "泌尿器科": 8,
    "放射線科": 6,
}

CBT_WEIGHTS = {
    # 基礎医学（コアカリ A〜C 領域）は採点対象のおよそ2割。
    "基礎医学": 65,
    # ブロック5・6（多選択肢・四連問）の形式枠。
    "多選択肢・4連問": 35,
    "医学総論・公衆衛生・診療の基本": 50,
    # --- 臓器別・全身性疾患の各論（D領域） ---
    "循環器": 22,
    "呼吸器": 20,
    "消化器": 22,
    "腎・泌尿器": 14,
    "内分泌・代謝": 14,
    "血液": 10,
    "免疫・膠原病": 8,
    "感染症": 10,
    "腫瘍": 8,
    "神経": 16,
    "皮膚": 8,
    "運動器": 8,
    "眼": 6,
    "耳鼻咽喉": 6,
    "精神": 8,
    "小児（成長と発達）": 10,
    "産婦人科": 12,
    # 2科目を統合したので重みも足し合わせる（5+10）。
    "救急・中毒・麻酔": 15,
}

WEIGHTS_BY_EXAM = {CBT: CBT_WEIGHTS, KOKUSHI: KOKUSHI_WEIGHTS}

# 正規の科目立てと1対1で対応していること。片方にだけ科目を足すと、
# その科目が目標問題数にも模試の出題比率にも現れず黙って抜け落ちる。
assert set(CBT_WEIGHTS) == set(CBT_CATEGORIES), set(CBT_WEIGHTS) ^ set(CBT_CATEGORIES)
assert set(KOKUSHI_WEIGHTS) == set(KOKUSHI_CATEGORIES), (
    set(KOKUSHI_WEIGHTS) ^ set(KOKUSHI_CATEGORIES)
)


def weights_for(exam_type):
    """試験種別の重み表。未知の試験種別は空の辞書（＝重み付けしない）。"""
    return WEIGHTS_BY_EXAM.get(exam_type, {})


def target_counts(exam_type, total, *, minimum=MIN_QUESTIONS_PER_CATEGORY):
    """科目ごとの目標問題数。

    まず全科目に ``minimum`` を配り、残りを出題構成比で比例配分する。
    ``total`` が最低数の合計に満たない場合は、全科目 ``minimum`` を返す
    （最低数の確保を比率より優先する）。
    """
    weights = weights_for(exam_type)
    if not weights:
        return {}
    base = {name: minimum for name in weights}
    extra = total - minimum * len(weights)
    if extra <= 0:
        return base

    total_weight = sum(weights.values())
    # 端数は「比例配分した実数」との差が大きい科目から1問ずつ配り、
    # 合計が extra ちょうどになるようにする（最大剰余方式）。
    exact = {name: extra * w / total_weight for name, w in weights.items()}
    for name, value in exact.items():
        base[name] += int(value)
    remaining = extra - sum(int(v) for v in exact.values())
    for name, _frac in sorted(
        exact.items(), key=lambda kv: (-(kv[1] % 1), kv[0])
    )[:remaining]:
        base[name] += 1
    return base


def share_of(exam_type, category):
    """その科目が本番の試験で占める割合（0〜1）。表に無ければ 0。"""
    weights = weights_for(exam_type)
    total = sum(weights.values())
    if not total:
        return 0.0
    return weights.get(category, 0) / total
