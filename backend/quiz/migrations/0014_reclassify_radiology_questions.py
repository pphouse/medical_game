"""放射線そのものを主題にした設問を「放射線科」に移す。

取り込み元が付けた分野をそのまま使っていたため、被曝線量・放射線治療の
適応・放射線事故といった「放射線科の問題」が、症例の舞台になっている科
（産科・眼科・整形外科など）に散っていた。放射線科は2問しかなく、演習の
単位として成立していない。

対象は設問文が下の語を含むものだけ。症例の中で画像検査や放射線治療が
手段として出てくるだけの問題（肺癌の治療方針など）は各論の科目に残す。
分野名（ID ではなく設問文）で判定するので、どのデータベースで流しても
同じ問題が動く。
"""

from django.db import migrations
from django.db.models import Q

TARGET = "放射線科"

# 「放射線そのもの」を問うている設問の語。
SUBJECT_MARKERS = [
    "放射線被ばく",
    "放射線被曝",
    "被曝線量",
    "被ばく線量",
    "密封線源",
    "放射性物質",
    "定位放射線",
    "放射線治療で最も",
    "放射線療法で最も",
    "放射線宿酔",
]


def move_to_radiology(apps, schema_editor):
    Question = apps.get_model("quiz", "Question")
    condition = Q()
    for marker in SUBJECT_MARKERS:
        condition |= Q(question_text__contains=marker)
    Question.objects.filter(exam_type="KOKUSHI").exclude(category=TARGET).filter(
        condition
    ).update(category=TARGET)


def noop(apps, schema_editor):
    """元の分野が何だったかは残していないので、戻す操作は用意しない。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0013_merge_emergency_family")]

    operations = [migrations.RunPython(move_to_radiology, noop)]
