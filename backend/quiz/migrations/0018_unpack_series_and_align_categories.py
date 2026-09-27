"""四連問を単問にほどき、公式の設問の分野を同梱データにそろえる。

1. 四連問（セットに属するタイプQの設問）を単問にほどく。四連問は、同じ症例で
   1問答えるたびに所見が明かされて臨床推論が進む、4問でひとつのストーリーに
   なった出題のこと。演習画面は設問を科目の一覧に1問ずつ並べ、どれからでも
   開ける作りなので、4問を順に解かせることができず、「四連問 2/4」の印だけが
   付いた単問になっていた。症例文を設問の頭に付けて（国試の連問をほどいた
   ときと同じ「症例文＋改行＋設問」）セットから外す。

2. 公式の設問の分野を、同梱データ（quiz/management/commands/data）の分野に
   そろえる。国試は blueprint_code、CBT は選択肢の並び（無ければ本文）で
   突き合わせる。同梱データの分野は1問ずつ確かめたもので、テスト
   （tests/test_shipped_data.py）が科目名の正しさを見ている。

   0014〜0017 は設問文の語で分野を決め直すので、同梱データと食い違う設問が
   出る（糸球体腎炎が選択肢の語に引かれて泌尿器になる、精巣腫瘍が放射線科を
   経て医学総論になる、など）。このマイグレーションをその後ろに置いて、
   最後に同梱データへそろえる。scripts/sql/fix_categories.sql と同じ内容で、
   どちらを先に当てても結果は同じになる。

3. 同梱データに無い設問（利用者の投稿など）は、分野名がその試験の科目名で
   ないときだけ normalize() で寄せる。
"""

import glob
import hashlib
import json
import os

from django.db import migrations

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "management",
    "commands",
    "data",
)


def _fingerprint(choices, key_field):
    joined = "|".join(f"{c.get(key_field)}:{c.get('text')}" for c in choices or [])
    return hashlib.md5(joined.encode("utf-8")).hexdigest()


def _shipped_categories():
    kokushi, cbt_by_choices, cbt_by_text = {}, {}, {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        if ".report." in path:
            continue
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        for item in payload.get("questions", []):
            if item["exam_type"] == "KOKUSHI":
                kokushi[item["blueprint_code"]] = item["category"]
            else:
                cbt_by_choices[_fingerprint(item["choices"], "id")] = item["category"]
                cbt_by_text[item["question_text"]] = item["category"]
    return kokushi, cbt_by_choices, cbt_by_text


def forwards(apps, schema_editor):
    from quiz.categories import CATEGORIES_BY_EXAM, normalize

    Question = apps.get_model("quiz", "Question")
    if not Question.objects.exists():
        return

    # 1) 四連問を単問にほどく。すでに症例文で始まる設問には付け足さない。
    for q in Question.objects.filter(question_set__isnull=False).select_related("question_set"):
        stem = q.question_set.case_stem or ""
        text = q.question_text or ""
        if stem and not text.startswith(stem):
            text = f"{stem}\n{text}"
        Question.objects.filter(pk=q.pk).update(
            question_text=text, question_type="M", question_set=None, set_order=None
        )

    # 2) 公式の設問は同梱データの分野に、3) それ以外は科目名でないときだけ寄せる。
    kokushi, cbt_by_choices, cbt_by_text = _shipped_categories()
    changed = []
    for q in Question.objects.only(
        "id", "exam_type", "blueprint_code", "choices", "question_text", "category"
    ).iterator(chunk_size=500):
        if q.exam_type == "KOKUSHI":
            want = kokushi.get(q.blueprint_code)
        else:
            want = cbt_by_choices.get(_fingerprint(q.choices, "key")) or cbt_by_text.get(
                q.question_text
            )
        if want is None and q.category not in CATEGORIES_BY_EXAM.get(q.exam_type, ()):
            want = normalize(q.category, q.question_text or "", q.blueprint_code, q.exam_type)
        if want and want != q.category:
            q.category = want
            changed.append(q)
    Question.objects.bulk_update(changed, ["category"], batch_size=500)


def noop(apps, schema_editor):
    """元の分野とセットは残していないので、戻す操作は用意しない。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0017_split_kidney_and_urology")]

    operations = [migrations.RunPython(forwards, noop)]
