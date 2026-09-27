"""本番に貼る設問の取り込み SQL（scripts/build_question_import_sql.py）が、
import_questions と同じ行をつくることを確かめる。

本番はデプロイで import_questions を流さないので、新しい設問は SQL で入れる。
SQL で入れた行と import_questions で入れた行が違うと、あとで import_questions を
流したときに同じ設問が二重に入ったり、分野や解説が食い違ったりする。
"""

import importlib.util
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import connection

from quiz.models import Question

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend" / "quiz" / "management" / "commands" / "data"

COMPARED = (
    "category", "topic", "difficulty", "exam_type", "question_text", "choices",
    "correct_choice_key", "explanation", "choice_explanations", "visibility",
    "question_type", "blueprint_code", "class_group", "status", "source",
    "correct_rate", "answer_count",
)


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_question_import_sql", ROOT / "scripts" / "build_question_import_sql.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows():
    return {
        (q.exam_type, q.question_text, json.dumps(q.choices, ensure_ascii=False)): {
            f: getattr(q, f) for f in COMPARED
        }
        for q in Question.objects.all()
    }


def _run(chunks):
    with connection.cursor() as cursor:
        for _, sql in chunks:
            cursor.execute(sql)
            added, existing, in_file = cursor.fetchone()
            assert added + existing == in_file


@pytest.mark.django_db
@pytest.mark.parametrize("batch", ["cbt_batch_basic_2026.json", "kokushi_106.json"])
def test_sql_creates_the_same_rows_as_import_questions(batch):
    # 小さく分けても、分け方で結果が変わらないことを見る
    chunks = _builder().statements([DATA / batch], chunk_bytes=150_000)
    assert len(chunks) > 1

    _run(chunks)
    via_sql = _rows()
    assert len(via_sql) == sum(n for n, _ in chunks)
    assert {r["status"] for r in via_sql.values()} == {Question.Status.PENDING}

    # 何度流しても増えない
    _run(chunks)
    assert Question.objects.count() == len(via_sql)

    # SQL で入れたあとに import_questions を流しても、1問も増えない
    call_command("import_questions", "--file", str(DATA / batch))
    assert Question.objects.count() == len(via_sql)

    # import_questions だけで入れた場合と、列の値まで一致する
    Question.objects.all().delete()
    call_command("import_questions", "--file", str(DATA / batch))
    assert _rows() == via_sql


def test_shipped_import_sql_is_up_to_date():
    """scripts/sql/import_cbt_basic_2026_*.sql が同梱データから作り直した結果と一致する。"""
    shipped = sorted((ROOT / "scripts" / "sql").glob("import_cbt_basic_2026_*.sql"))
    assert shipped, "scripts/sql/import_cbt_basic_2026_*.sql が無い"
    builder = _builder()
    chunks = builder.statements([DATA / "cbt_batch_basic_2026.json"])
    assert len(chunks) == len(shipped)
    for i, ((count, sql), path) in enumerate(zip(chunks, shipped, strict=True), start=1):
        expected = builder.header(
            "import_cbt_basic_2026", i, len(chunks), count, ["cbt_batch_basic_2026.json"]
        ) + sql
        assert path.read_text(encoding="utf-8") == expected, (
            f"{path.name} が古い。python scripts/build_question_import_sql.py "
            "import_cbt_basic_2026 cbt_batch_basic_2026.json で作り直す"
        )
