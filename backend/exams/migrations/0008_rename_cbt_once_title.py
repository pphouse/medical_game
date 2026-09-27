"""作成済みのCBT模試のタイトルから「（生涯1回）」を外す。

表示は「1度だけ受験できます」に統一したので、既に作られている回の
タイトルも合わせる。回数の制限そのものは変わらない。
"""

from django.db import migrations

OLD = "CBT全国模試（生涯1回）"
NEW = "CBT全国模試"


def rename(apps, schema_editor):
    apps.get_model("exams", "MockExam").objects.filter(
        kind="cbt_once", title=OLD
    ).update(title=NEW)


def unrename(apps, schema_editor):
    apps.get_model("exams", "MockExam").objects.filter(
        kind="cbt_once", title=NEW
    ).update(title=OLD)


class Migration(migrations.Migration):
    dependencies = [("exams", "0007_monthly_kokushi_is_for_fifth_year_and_up")]

    operations = [migrations.RunPython(rename, unrename)]
