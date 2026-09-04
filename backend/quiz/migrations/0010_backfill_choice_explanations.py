"""解説本文に畳み込まれていた選択肢ごとの解説を、専用の項目へ移す。

これまでは本文の末尾に「【誤答選択肢の解説】」の見出しで文字列として
持っていた。選択肢の横に並べて表示したいので、構造化して
Question.choice_explanations に入れる。
"""

from django.db import migrations

BATCH = 500


def move_to_field(apps, schema_editor):
    from quiz.choice_explanations import BLOCK_HEADING, split_choice_explanations

    Question = apps.get_model("quiz", "Question")
    pending = []
    qs = Question.objects.filter(explanation__contains=BLOCK_HEADING)
    for q in qs.iterator(chunk_size=BATCH):
        body, per_choice = split_choice_explanations(q.explanation)
        if not per_choice:
            continue
        q.explanation = body
        q.choice_explanations = per_choice
        pending.append(q)
        if len(pending) >= BATCH:
            Question.objects.bulk_update(pending, ["explanation", "choice_explanations"])
            pending.clear()
    if pending:
        Question.objects.bulk_update(pending, ["explanation", "choice_explanations"])


def fold_back_into_text(apps, schema_editor):
    from quiz.choice_explanations import merge_into_text

    Question = apps.get_model("quiz", "Question")
    pending = []
    for q in Question.objects.exclude(choice_explanations={}).iterator(chunk_size=BATCH):
        q.explanation = merge_into_text(q.explanation, q.choice_explanations)
        q.choice_explanations = {}
        pending.append(q)
        if len(pending) >= BATCH:
            Question.objects.bulk_update(pending, ["explanation", "choice_explanations"])
            pending.clear()
    if pending:
        Question.objects.bulk_update(pending, ["explanation", "choice_explanations"])


class Migration(migrations.Migration):
    dependencies = [("quiz", "0009_question_choice_explanations")]

    operations = [migrations.RunPython(move_to_field, fold_back_into_text)]
