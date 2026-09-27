"""問題数が少なすぎる科目を整理する。

演習の単位として成立するには1科目あたり10問以上ほしい。国試側で10問に
届かない3科目を、次のように扱う。

* 免疫・膠原病 (7問) … 膠原病そのものを主題にした設問が他の科に散って
  いたので集める（7 → 12問）。臓器合併症を問う各論の症例は動かさない。
* 放射線科 (7問) … 集め直しても10問に届かないので医学総論へ統合する。
  CBT 側でも放射線は「医学総論・公衆衛生・診療の基本」に入っている。
* 必修問題 (0問) … 分野ではなく出題形式（B・Eブロック）の呼び名で、
  科目として持つ中身が無い。科目立てから外す。

設問文で判定するので、どのデータベースで流しても同じ問題が動く。
"""

from django.db import migrations
from django.db.models import Q

# 膠原病そのものを主題にした設問の語。症例（「◯歳の」で始まる臨床問題）は
# 臓器の科に残す — 合併症としての記述であることが多いため。
IMMUNOLOGY_MARKERS = [
    "関節リウマチの",
    "膠原病",
    "自己抗体と",
    "抗リン脂質抗体症候群",
    "好中球の構成成分に対する自己抗体",
    "ANCA関連",
    "Sjögren症候群",
    "シェーグレン症候群",
    "皮膚筋炎",
    "多発性筋炎",
    "全身性強皮症",
    "ベーチェット",
    "成人Still病",
    "リウマチ性多発筋痛症",
    "結節性多発動脈炎",
    "顕微鏡的多発血管炎",
    "巨細胞性動脈炎",
]


def consolidate(apps, schema_editor):
    Question = apps.get_model("quiz", "Question")
    kokushi = Question.objects.filter(exam_type="KOKUSHI")

    # 1) 膠原病そのものを主題にした設問を集める（症例問題は除く）
    markers = Q()
    for marker in IMMUNOLOGY_MARKERS:
        markers |= Q(question_text__contains=marker)
    kokushi.exclude(category="免疫・膠原病").exclude(
        question_text__contains="歳の"
    ).filter(markers).update(category="免疫・膠原病")

    # 2) 放射線科・必修問題は科目として持たず、医学総論にまとめる
    kokushi.filter(category__in=["放射線科", "必修問題"]).update(category="医学総論")


def noop(apps, schema_editor):
    """元の分野は残していないので、戻す操作は用意しない。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0015_merge_urology_into_kidney")]

    operations = [migrations.RunPython(consolidate, noop)]
