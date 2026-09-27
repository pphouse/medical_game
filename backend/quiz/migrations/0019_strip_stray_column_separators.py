"""設問文と選択肢に紛れ込んだ列区切りを取り除く。

国試の設問は厚生労働省のPDFから取り込んでいる。組合せ問題の左右2列を
見分けるため、字間の広い箇所に "—" を差し込んでいる（scripts/import_kokushi.py）
のだが、均等割りで広がった字間まで列の境目と誤認され、「Bell麻痺— の症状」
「急性好酸球性— 肺炎」のように語の途中へ入っていた。

同梱している設問データ（data/*.json）は直してあり、検査
（tests/test_shipped_data.py::test_no_stray_column_separator）も通っている。
取り込み済みのデータベースにだけ古い本文が残っているので、ここで直す。

直し方は3通り。

* 区切りの直後に ":" が続くもの … 区切りが二重に入っている。"—" を落とす。
* 組合せ問題の選択肢 … 列の境目そのものなので、前後に空白を入れた
  正しい区切り " — " に直す。
* それ以外 … 語の途中に紛れ込んだものなので、続く空白ごと落とす。

前後に空白のある "—" は正しい区切りなので触らない。
"""

import re

from django.db import migrations

# 直前が空白でない "—"（＝語の途中に入ったもの）と、それに続く空白。
IN_WORD = re.compile(r"(?<=\S)—\s*")
# 行頭の "—"。選択肢の先頭に区切りだけが残っていることがある。
AT_HEAD = re.compile(r"^—\s*")
# 区切りが二重に入った "— :"。
BEFORE_COLON = re.compile(r"—\s*([:：])")


def clean(text, *, keep_as_separator=False):
    if not text or "—" not in text:
        return text
    fixed = BEFORE_COLON.sub(r"\1", text)
    replacement = " — " if keep_as_separator else ""
    fixed = IN_WORD.sub(replacement, fixed)
    fixed = AT_HEAD.sub("" if keep_as_separator else "", fixed)
    return fixed


def strip_separators(apps, schema_editor):
    Question = apps.get_model("quiz", "Question")
    changed = []
    for question in Question.objects.all().only("id", "question_text", "choices"):
        text = clean(question.question_text)
        # 組合せ問題の選択肢だけは、列の境目として区切りを残す。設問文の
        # ほうは列組みではないので、組合せ問題でも落としてよい。
        combination = "組合せ" in (question.question_text or "")
        choices = [
            {**c, "text": clean(c.get("text", ""), keep_as_separator=combination)}
            for c in (question.choices or [])
        ]
        if text != question.question_text or choices != question.choices:
            question.question_text = text
            question.choices = choices
            changed.append(question)
    if changed:
        Question.objects.bulk_update(changed, ["question_text", "choices"])

    QuestionSet = apps.get_model("quiz", "QuestionSet")
    sets = []
    for question_set in QuestionSet.objects.all().only("id", "case_stem"):
        stem = clean(question_set.case_stem)
        if stem != question_set.case_stem:
            question_set.case_stem = stem
            sets.append(question_set)
    if sets:
        QuestionSet.objects.bulk_update(sets, ["case_stem"])


def noop(apps, schema_editor):
    """落とした区切りがどこに在ったかは残していないので、戻す操作は無い。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0018_split_radiology_and_anesthesia")]

    operations = [migrations.RunPython(strip_separators, noop)]
