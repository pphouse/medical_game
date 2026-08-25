from django.db import migrations, models


def reset_points(apps, schema_editor):
    """ランクの意味づけが変わったので累計ポイントを0に戻す。

    旧: points=1000 が全員の初期値で、ランクは他人との相対位置（上位%）で決まった。
    新: points はランクの絶対位置そのもの（100ごとに D→C→B→A→S→SS）。
    旧データをそのまま残すと 1000 = SS になってしまうため、全員 D の 0% から
    やり直す。ranked_matches は対戦回数の記録なのでそのまま残す。
    """
    apps.get_model("accounts", "Profile").objects.update(points=0)


def noop(apps, schema_editor):
    """逆方向は復元不能（元の値を保持していない）。スキーマだけ戻す。"""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_profile_exam_preference"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="points",
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(reset_points, noop),
    ]
