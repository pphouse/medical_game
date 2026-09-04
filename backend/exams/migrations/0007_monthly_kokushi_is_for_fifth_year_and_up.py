"""月次実力テストの国試版を5年生以上に限定する。

作成時は学年制限なし（全学年に表示）だったので、既に作られている回にも
同じ制限を入れる。4年生以下には国試の模試を出さない方針にそろえる。
"""

from django.db import migrations


def restrict_monthly_kokushi(apps, schema_editor):
    MockExam = apps.get_model("exams", "MockExam")
    MockExam.objects.filter(
        kind="monthly", exam_type="KOKUSHI", target_grade_min__isnull=True
    ).update(target_grade_min=5)


def unrestrict_monthly_kokushi(apps, schema_editor):
    MockExam = apps.get_model("exams", "MockExam")
    MockExam.objects.filter(
        kind="monthly", exam_type="KOKUSHI", target_grade_min=5
    ).update(target_grade_min=None)


class Migration(migrations.Migration):
    dependencies = [("exams", "0006_alter_mockexam_kind")]

    operations = [
        migrations.RunPython(restrict_monthly_kokushi, unrestrict_monthly_kokushi),
    ]
