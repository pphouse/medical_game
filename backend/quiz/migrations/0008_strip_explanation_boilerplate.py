"""取り込み済みの解説から、出典URL・整形の注記などの定型文を消す。

取り込み時（import_questions）にも落としているが、それ以前に取り込んだ
ぶんが残っているので、デプロイ時にまとめて掃除する。同じ内容は
manage.py strip_explanation_boilerplate でも流せる。

元に戻す方法は無い（消した定型文は復元しない）ので、逆向きは何もしない。
"""

from django.db import migrations

BATCH = 500


def strip(apps, schema_editor):
    from quiz.explanations import strip_boilerplate

    Question = apps.get_model("quiz", "Question")
    pending = []
    for q in Question.objects.exclude(explanation="").iterator(chunk_size=BATCH):
        cleaned = strip_boilerplate(q.explanation)
        if cleaned == q.explanation:
            continue
        q.explanation = cleaned
        pending.append(q)
        if len(pending) >= BATCH:
            Question.objects.bulk_update(pending, ["explanation"])
            pending.clear()
    if pending:
        Question.objects.bulk_update(pending, ["explanation"])


class Migration(migrations.Migration):
    dependencies = [("quiz", "0007_reviewreminder")]

    operations = [migrations.RunPython(strip, migrations.RunPython.noop)]
