"""作成済みのCBT模試に、受験可能期間（7月1日〜翌3月31日）を入れる。

以前は締切を表す手段がなく end_at に100年後を入れて「常時受験可」にして
いた。年度ごとに1回・7月1日から翌3月31日までに変えたので、既存の回も
その年度の期間に収める。

日付の計算はこのファイル内で完結させる（コマンド側の定数が将来変わっても、
このマイグレーションが当時の意図どおりに走るようにするため）。
"""

import datetime

from django.db import migrations

JST = datetime.timezone(datetime.timedelta(hours=9))


def window_for(created_at):
    """``created_at`` が属する年度の受験可能期間を返す。"""
    local = created_at.astimezone(JST)
    year = local.year if (local.month, local.day) >= (4, 1) else local.year - 1
    return (
        datetime.datetime(year, 7, 1, 0, 0, tzinfo=JST),
        datetime.datetime(year + 1, 3, 31, 23, 59, 59, tzinfo=JST),
    )


def set_window(apps, schema_editor):
    MockExam = apps.get_model("exams", "MockExam")
    for exam in MockExam.objects.filter(kind="cbt_once"):
        opens, closes = window_for(exam.start_at)
        MockExam.objects.filter(pk=exam.pk).update(start_at=opens, end_at=closes)


class Migration(migrations.Migration):
    dependencies = [("exams", "0009_alter_mockexam_kind_label")]

    # 元の「100年後」に戻す意味はないので、逆向きは何もしない。
    operations = [migrations.RunPython(set_window, migrations.RunPython.noop)]
