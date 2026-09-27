"""腫瘍マーカーの設問から、選択肢と解説の日本語名を外す。

選択肢が「癌胎児性抗原（CEA）」のように和名＋略号の併記になっていた。
実際の試験でも臨床でも略号で書かれるので、和名を残すと選択肢が長くなる
だけで、どのマーカーを指しているのかは略号で足りる。

取り込み元のバッチ（data/cbt_batch_core_2026.json）も同じ内容に直して
あるが、import_questions は設問文で既存を判定して上書きしないため、
すでに取り込まれている分はここで直す。
"""

from django.db import migrations

QUESTION_TEXT_STARTS_WITH = "68歳の男性。6か月前から便が細くなり"

ABBREVIATIONS = {"A": "CEA", "B": "AFP", "C": "PSA", "D": "CA15-3", "E": "NSE"}
OLD_EXPLANATION_PREFIX = "CEA（癌胎児性抗原）は"
NEW_EXPLANATION_PREFIX = "CEAは"


def drop_japanese_names(apps, schema_editor):
    Question = apps.get_model("quiz", "Question")
    for question in Question.objects.filter(
        question_text__startswith=QUESTION_TEXT_STARTS_WITH
    ):
        choices = [
            {**choice, "text": ABBREVIATIONS.get(choice.get("key"), choice.get("text"))}
            for choice in question.choices or []
        ]
        explanation = (question.explanation or "").replace(
            OLD_EXPLANATION_PREFIX, NEW_EXPLANATION_PREFIX, 1
        )
        Question.objects.filter(pk=question.pk).update(
            choices=choices, explanation=explanation
        )


def noop(apps, schema_editor):
    """和名を戻す意味はないので、逆向きは何もしない。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0011_merge_toxicology_into_emergency")]

    operations = [migrations.RunPython(drop_japanese_names, noop)]
