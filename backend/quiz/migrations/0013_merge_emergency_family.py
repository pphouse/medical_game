"""救急・中毒・麻酔の旧名をすべて「救急・中毒・麻酔」にまとめる。

救急／中毒／麻酔科は1つの科目にしてあるのに、取り込み時期によって
「中毒・環境異常症」「中毒・環境」「救急」「麻酔科」…と別々の名前で
残っていて、同じ科目の中身が一覧に分かれて並んでいた。

0011 は「中毒・環境異常症」だけを対象にしていたが、他の旧名も同じ科目な
のでここでまとめて寄せる。読み替え表（quiz.categories）に入っている名前と
同じ内容なので、reclassify_categories を流しても同じ結果になる。
"""

from django.db import migrations

TARGET = "救急・中毒・麻酔"
LEGACY_NAMES = [
    "中毒",
    "中毒・環境",
    "中毒・環境異常症",
    "中毒・物理化学的因子",
    "救急",
    "救急系",
    "救急・中毒",
    "救急・集中治療",
    "麻酔",
    "麻酔科",
]


def merge(apps, schema_editor):
    apps.get_model("quiz", "Question").objects.filter(
        category__in=LEGACY_NAMES
    ).update(category=TARGET)


def noop(apps, schema_editor):
    """まとめたあとは元がどれだったか分からないので、戻す操作は用意しない。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0012_tumor_marker_choices_abbreviation_only")]

    operations = [migrations.RunPython(merge, noop)]
