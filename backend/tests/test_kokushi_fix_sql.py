"""公開中の国試を直す SQL（scripts/build_kokushi_fix_sql.py）の検査。

本番はデプロイでデータを入れないので、取り込み直して直した本文は SQL で
当てる。直す前の本番の状態（scripts/kokushi_fix/2026-09.json の控え）を
テスト用のDBに作り、SQL を流して、同梱データどおりになることを確かめる。
"""

import importlib.util
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import connection

from quiz.management.commands.import_questions import question_fields
from quiz.models import Question

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend" / "quiz" / "management" / "commands" / "data"
STORED = ("question_text", "choices", "explanation", "choice_explanations")


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_kokushi_fix_sql", ROOT / "scripts" / "build_kokushi_fix_sql.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _current():
    out = {}
    for exam in range(114, 120):
        payload = json.loads((DATA / f"kokushi_{exam}.json").read_text(encoding="utf-8"))
        out.update({q["blueprint_code"]: q for q in payload["questions"]})
    return out


def _run(sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()


def test_shipped_fix_sql_is_up_to_date():
    files, _, _ = _builder().build()
    shipped = sorted((ROOT / "scripts" / "sql").glob("kokushi_fix_2026_09*.sql"))
    assert [p.name for p in shipped] == sorted(files), "python scripts/build_kokushi_fix_sql.py で作り直す"
    for path in shipped:
        assert path.read_text(encoding="utf-8") == files[path.name], (
            f"{path.name} が古い。python scripts/build_kokushi_fix_sql.py で作り直す"
        )


@pytest.mark.django_db
def test_fix_brings_production_rows_to_the_shipped_data():
    builder = _builder()
    snapshot = json.loads(builder.SNAPSHOT.read_text(encoding="utf-8"))
    current = _current()
    files, n_fix, _ = builder.build()
    assert n_fix == len(snapshot["before"]) > 0

    # 直す前の本番: 控えの本文で、公開済みの行
    for code, before in snapshot["before"].items():
        fields = question_fields({**current[code], **before})
        Question.objects.create(**{**fields, "status": Question.Status.PUBLISHED})
    # 審査で本文に手を入れた行は上書きしない
    edited = sorted(snapshot["before"])[0]
    Question.objects.filter(blueprint_code=edited).update(question_text="審査で直した本文")

    result = dict(_run(files["kokushi_fix_2026_09.sql"]))
    assert result.pop(edited) == "本文が控えと違う（手で確認）"
    assert set(result.values()) == {"直した"}

    for code in result:
        row = Question.objects.get(exam_type="KOKUSHI", blueprint_code=code)
        expected = question_fields(current[code])
        assert {f: getattr(row, f) for f in STORED} == {f: expected[f] for f in STORED}, code
        assert row.status == Question.Status.PUBLISHED  # 公開の状態は変えない
    assert Question.objects.get(blueprint_code=edited).question_text == "審査で直した本文"

    # 何度流しても同じ
    again = dict(_run(files["kokushi_fix_2026_09.sql"]))
    again.pop(edited)
    assert set(again.values()) == {"すでに直っている"}

    # 増えた設問を入れる。直した設問は同じ blueprint_code の行があるので入らない
    before_count = Question.objects.count()
    added = 0
    for name in sorted(n for n in files if "_add_" in n):
        (n_added, n_existing, n_rows), = _run(files[name])
        assert n_added + n_existing == n_rows
        added += n_added
    new_codes = set(current) - set(snapshot["known_codes"])
    assert added == len(new_codes) > 0
    assert Question.objects.count() == before_count + added
    assert not Question.objects.filter(blueprint_code__in=new_codes).exclude(
        status=Question.Status.PENDING
    ).exists()
    for name in sorted(n for n in files if "_add_" in n):
        (n_added, _, _), = _run(files[name])
        assert n_added == 0

    # あとで import_questions を流しても、直した設問が二重にならない
    call_command("import_questions", "--file", str(DATA / "kokushi_114.json"))
    for code in snapshot["before"]:
        if code.startswith("114-"):
            assert Question.objects.filter(exam_type="KOKUSHI", blueprint_code=code).count() == 1, code
