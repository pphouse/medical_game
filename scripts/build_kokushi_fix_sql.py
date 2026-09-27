#!/usr/bin/env python3
"""公開中の国試（第114〜119回）を、取り込み直した同梱データに合わせる SQL を作る。

2026年9月に国試PDFの字を字形で決めるようにし（scripts/import_kokushi.py）、
取り込み直したところ、公開中の設問に化けが見つかった。括弧や符号が別の記号に
なったもの（「糖:−<」は「糖（−）」）、連問の症例文の続きが前の設問の選択肢に
付いていたもの（第114回B43の選択肢が699字、B44 は症例の後半を欠いていた）、
以前の手直しが推測で誤っていたもの（第114回B33「右下肢」は PDF では「右下腿」）。
同じ取り込みで、これまで落ちていた設問も増えた。

本番はデプロイでデータを入れないので SQL で直す。2本に分ける。

  kokushi_fix_2026_09.sql       本文を直す（UPDATE）
  kokushi_fix_2026_09_add_NN.sql 増えた設問を入れる（INSERT、status は pending）

直す前の本番の状態は scripts/kokushi_fix/2026-09.json に控えてある（直す前の
コミットから --snapshot で作った）。UPDATE は、本番の行が控えと同じ本文・選択肢の
ときだけ当てる。審査で手を入れた行を上書きしないため。当たらなかった行は最後の
表に「手で確認」と出る。何度流しても結果は同じ。

使い方:
    python scripts/build_kokushi_fix_sql.py                  # SQL を作り直す
    python scripts/build_kokushi_fix_sql.py --snapshot REF   # 控えを REF から作る（一度きり）
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backend/quiz/management/commands/data"
SNAPSHOT = ROOT / "scripts/kokushi_fix/2026-09.json"
OUT_DIR = ROOT / "scripts/sql"
NAME = "kokushi_fix_2026_09"
ROUNDS = tuple(range(114, 120))

sys.path.insert(0, str(ROOT / "scripts"))
import build_question_import_sql as import_sql  # noqa: E402


def _paths():
    return [DATA_DIR / f"kokushi_{r}.json" for r in ROUNDS]


def _questions(payload):
    return {q["blueprint_code"]: q for q in payload["questions"]}


def _stored(q):
    """本番の行に入っている値（取り込みと同じ変換を通す）。"""
    from quiz.management.commands.import_questions import question_fields

    fields = question_fields(q)
    return {k: fields[k] for k in ("question_text", "choices", "explanation", "choice_explanations")}


def make_snapshot(ref):
    """直す前のコミット ref の同梱データから控えを作る。"""
    known, before = [], {}
    for path in _paths():
        rel = path.relative_to(ROOT).as_posix()
        old = _questions(json.loads(subprocess.check_output(["git", "show", f"{ref}:{rel}"], cwd=ROOT)))
        new = _questions(json.loads(path.read_text(encoding="utf-8")))
        known += sorted(old)
        for code, q in old.items():
            if code in new and _stored(q) != _stored(new[code]):
                before[code] = {
                    "question_text": q["question_text"],
                    "choices": q["choices"],
                    "explanation": q["explanation"],
                    "correct_choice_id": q["correct_choice_id"],
                }
    snapshot = {
        "note": (
            "第114〜119回の、取り込み直す前の同梱データ（本番に入っている状態）。"
            f"コミット {ref} から scripts/build_kokushi_fix_sql.py --snapshot で作った。"
        ),
        "known_codes": known,
        "before": before,
    }
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{SNAPSHOT.relative_to(ROOT)}: 公開中 {len(known)}問、直す {len(before)}問")


def _jsonb(value):
    return import_sql.lit(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def update_statement(snapshot):
    """本文を直す UPDATE と、結果の表。"""
    current = {}
    for path in _paths():
        current.update(_questions(json.loads(path.read_text(encoding="utf-8"))))

    rows = []
    for code in sorted(snapshot["before"], key=lambda c: (c.split("-")[0], c.split("-")[1], int(c.split("-")[2]))):
        before = snapshot["before"][code]
        now = current[code]
        if before["correct_choice_id"] != now["correct_choice_id"]:
            raise SystemExit(f"{code}: 正答が変わっている。本文の直しとは別に扱う")
        old, new = _stored({**now, **before}), _stored(now)
        rows.append(
            "    ("
            + ", ".join([
                import_sql.lit(code),
                import_sql.lit(old["question_text"]), _jsonb(old["choices"]),
                import_sql.lit(new["question_text"]), _jsonb(new["choices"]),
                import_sql.lit(new["explanation"]), _jsonb(new["choice_explanations"]),
            ])
            + ")"
        )
    sql = (
        "WITH v (blueprint_code, old_text, old_choices, question_text, choices,"
        " explanation, choice_explanations) AS (VALUES\n"
        + ",\n".join(rows)
        + "\n),\nfixed AS (\n"
        "    UPDATE quiz_question AS q\n"
        "    SET question_text = v.question_text,\n"
        "        choices = v.choices,\n"
        "        explanation = v.explanation,\n"
        "        choice_explanations = v.choice_explanations\n"
        "    FROM v\n"
        "    WHERE q.exam_type = 'KOKUSHI'\n"
        "      AND q.blueprint_code = v.blueprint_code\n"
        "      AND q.question_text = v.old_text\n"
        "      AND q.choices = v.old_choices\n"
        "    RETURNING q.blueprint_code\n"
        ")\n"
        "SELECT v.blueprint_code AS \"設問\",\n"
        "       CASE\n"
        "         WHEN v.blueprint_code IN (SELECT blueprint_code FROM fixed) THEN '直した'\n"
        "         WHEN EXISTS (SELECT 1 FROM quiz_question q WHERE q.exam_type = 'KOKUSHI'\n"
        "                        AND q.blueprint_code = v.blueprint_code\n"
        "                        AND q.question_text = v.question_text AND q.choices = v.choices)\n"
        "           THEN 'すでに直っている'\n"
        "         WHEN EXISTS (SELECT 1 FROM quiz_question q WHERE q.exam_type = 'KOKUSHI'\n"
        "                        AND q.blueprint_code = v.blueprint_code)\n"
        "           THEN '本文が控えと違う（手で確認）'\n"
        "         ELSE '本番に無い（_add の SQL で入る）'\n"
        "       END AS \"結果\"\n"
        "FROM v\n"
        "ORDER BY 2 DESC, 1;\n"
    )
    header = "\n".join([
        f"-- 公開中の国試の本文を直す（{len(rows)}問）。scripts/build_kokushi_fix_sql.py で作り直せる。",
        "-- 本番の行が直す前の本文・選択肢のときだけ当てる（審査で手を入れた行は上書きしない）。",
        "-- 何度流しても結果は同じ。最後の表で全問が「直した」か「すでに直っている」なら完了。",
        "-- 「手で確認」が出たら、その設問は審査画面で本文を見比べて直す。",
        "",
    ])
    return header + sql, len(rows)


def add_codes(snapshot):
    """入れる設問: 増えた設問と、直した設問（本番に無ければ入れる）。"""
    current = set()
    for path in _paths():
        current |= set(_questions(json.loads(path.read_text(encoding="utf-8"))))
    return (current - set(snapshot["known_codes"])) | set(snapshot["before"])


def build(out_dir=OUT_DIR):
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    files = {}
    update_sql, n_fix = update_statement(snapshot)
    files[f"{NAME}.sql"] = update_sql

    codes = add_codes(snapshot)
    chunks = import_sql.statements(_paths(), only=codes)
    sources = [p.name for p in _paths()]
    for i, (count, sql) in enumerate(chunks, start=1):
        head = import_sql.header(f"{NAME}_add", i, len(chunks), count, sources)
        files[f"{NAME}_add_{i:02d}.sql"] = head + sql
    return files, n_fix, sum(n for n, _ in chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", metavar="REF", help="直す前のコミットから控えを作る")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_DEBUG", "true")
    from _django import setup_django

    setup_django()

    if args.snapshot:
        make_snapshot(args.snapshot)
        return 0

    files, n_fix, n_add = build()
    for old in OUT_DIR.glob(f"{NAME}*.sql"):
        old.unlink()
    for name, text in files.items():
        (OUT_DIR / name).write_text(text, encoding="utf-8")
        print(f"  scripts/sql/{name}  {len(text.encode()) / 1000:.0f}KB")
    print(f"直す {n_fix}問 / 入れる候補 {n_add}問")
    return 0


if __name__ == "__main__":
    sys.exit(main())
