"""「泌尿器科」を「腎・泌尿器」に統合する。

国試の章立てに腎・泌尿器と泌尿器科の両方があり、中身が被っていた。
同じ臓器の問題が2つの科目に分かれて並び、どちらを開けばいいのか
分からない。問題数の多い「腎・泌尿器」に寄せ、「泌尿器科」は科目立てから
外した。

読み替え表（quiz.categories）にも入れてあるので、reclassify_categories を
流しても同じ結果になる。
"""

from django.db import migrations

TARGET = "腎・泌尿器"
LEGACY_NAMES = ["泌尿器科", "泌尿器", "泌尿器系"]


def merge(apps, schema_editor):
    apps.get_model("quiz", "Question").objects.filter(
        category__in=LEGACY_NAMES
    ).update(category=TARGET)


def noop(apps, schema_editor):
    """まとめたあとは元がどちらだったか分からないので、戻す操作は用意しない。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0014_reclassify_radiology_questions")]

    operations = [migrations.RunPython(merge, noop)]
