"""旧分野「中毒・環境異常症」を「救急・中毒・麻酔」に統一する。

救急・中毒・麻酔科は1つの科目にまとめてあるのに、取り込み時期の違いで
「中毒・環境異常症」という旧名の問題が別の科目として一覧に並んでいた。
同じ科目の中身が2つに割れていて、どちらを開けばいいのか分からない。

分野名の読み替え表（quiz.categories）には元から入っているので、
reclassify_categories を流しても同じ結果になる。デプロイ時に確実に
そろえるためマイグレーションにしておく。
"""

from django.db import migrations

OLD = "中毒・環境異常症"
NEW = "救急・中毒・麻酔"


def merge(apps, schema_editor):
    apps.get_model("quiz", "Question").objects.filter(category=OLD).update(category=NEW)


def unmerge(apps, schema_editor):
    """統一後は元がどちらだったか分からないので、戻す操作は用意しない。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0010_backfill_choice_explanations")]

    operations = [migrations.RunPython(merge, unmerge)]
