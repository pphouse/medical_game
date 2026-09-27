"""0018: 四連問を単問にほどき、公式の設問の分野を同梱データにそろえる。"""

import importlib
import json
from pathlib import Path

import pytest
from django.apps import apps as django_apps

from quiz.models import Question, QuestionSet

pytestmark = pytest.mark.django_db

migration = importlib.import_module("quiz.migrations.0018_unpack_series_and_align_categories")
DATA = Path(__file__).resolve().parent.parent / "quiz/management/commands/data"


def run():
    migration.forwards(django_apps, None)


def shipped(file, key, value):
    payload = json.loads((DATA / file).read_text(encoding="utf-8"))
    return next(q for q in payload["questions"] if q[key] == value)


def create(**fields):
    defaults = dict(
        exam_type="CBT",
        difficulty=2,
        correct_choice_key="A",
        explanation="",
        status=Question.Status.PUBLISHED,
        choices=[{"key": k, "text": f"選択肢{k}"} for k in "ABCDE"],
    )
    return Question.objects.create(**{**defaults, **fields})


def test_series_are_unpacked_once():
    """症例文を頭に付けてセットから外す。2回流しても二重にならない。"""
    qset = QuestionSet.objects.create(title="t", case_stem="68歳の男性。胸痛で来院した。")
    steps = [
        create(
            category="循環器",
            question_text=f"第{i}問の設問文。",
            question_type=Question.QuestionType.SEQUENTIAL,
            question_set=qset,
            set_order=i,
            choices=[{"key": k, "text": f"{i}-{k}"} for k in "ABCDE"],
        )
        for i in (1, 2)
    ]
    run()
    run()
    for i, step in enumerate(steps, 1):
        step.refresh_from_db()
        assert step.question_text == f"68歳の男性。胸痛で来院した。\n第{i}問の設問文。"
        assert step.question_type == Question.QuestionType.MULTIPLE_CHOICE
        assert step.question_set_id is None and step.set_order is None


def test_official_questions_follow_the_shipped_category():
    """同梱データの分野にそろえる（科目名であっても食い違えば直す）。

    0017 は設問文の語で腎臓／泌尿器に分けるので、糸球体腎炎が泌尿器に、
    0014・0016 を経て精巣腫瘍が医学総論に入ることがある。
    """
    iga = shipped("cbt_batch_core_2026.json", "id", "core2026-586")
    cbt = create(
        category="泌尿器",
        question_text=iga["question_text"],
        choices=[{"key": c["id"], "text": c["text"]} for c in iga["choices"]],
    )
    testis = shipped("kokushi_118.json", "blueprint_code", "118-A-16")
    kokushi = create(
        exam_type="KOKUSHI",
        category="医学総論",
        blueprint_code="118-A-16",
        question_text=testis["question_text"],
    )
    run()
    cbt.refresh_from_db()
    kokushi.refresh_from_db()
    assert cbt.category == iga["category"] == "腎臓"
    assert kokushi.category == testis["category"] == "泌尿器"


def test_unknown_questions_are_fixed_only_when_the_name_is_not_a_subject():
    """同梱データに無い設問は、科目名でないときだけ寄せる（管理画面での付け替えは残す）。"""
    kept = create(category="呼吸器", question_text="投稿された設問（科目名）")
    fixed = create(category="麻酔", question_text="投稿された設問（旧い名前）")
    run()
    kept.refresh_from_db()
    fixed.refresh_from_db()
    assert kept.category == "呼吸器"
    assert fixed.category == "救急・中毒・麻酔"
