#!/usr/bin/env python3
"""同梱の設問バッチを、本番の SQL Editor に貼って取り込める SQL にする。

本番はデプロイで import_questions を流さないので、新しい設問は SQL で入れる。
値は import_questions と同じ変換（question_fields）を通したもので、重複の
判定も同じ（exam_type・本文・選択肢が同じ行がすでにあれば入れない）。
status は必ず pending で、人の医学的レビューで公開するまで学習者には出ない。
何度流しても結果は同じ。

Supabase の SQL Editor は1回に貼れる量が1MB前後までなので、1本あたり
CHUNK_BYTES を超えないように分ける。どのファイルも1つの文で完結していて、
順番は問わない。流すと「追加した問題／すでにあった問題」の表が出る。

使い方:
    python scripts/build_question_import_sql.py import_cbt_basic_2026 cbt_batch_basic_2026.json
    python scripts/build_question_import_sql.py import_kokushi_106_113 kokushi_106.json kokushi_107.json ...
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backend/quiz/management/commands/data"
OUT_DIR = ROOT / "scripts/sql"
CHUNK_BYTES = 450_000

# quiz_question の NOT NULL の列のうち、バッチから決まるもの。残りの
# correct_rate・answer_count・created_at は INSERT で 0・0・now() を入れる。
COLUMNS = (
    "category", "topic", "difficulty", "exam_type", "question_text", "choices",
    "correct_choice_key", "explanation", "choice_explanations", "visibility",
    "question_type", "blueprint_code", "class_group", "status", "source",
)
JSON_COLUMNS = {"choices", "choice_explanations"}


def lit(value):
    """SQL のリテラル。"""
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def value_row(fields):
    parts = []
    for column in COLUMNS:
        value = fields[column]
        if column in JSON_COLUMNS:
            parts.append(lit(json.dumps(value, ensure_ascii=False)) + "::jsonb")
        else:
            parts.append(lit(value))
    return "(" + ", ".join(parts) + ")"


def insert_statement(rows):
    """1本ぶんの INSERT。1つの文なので途中で失敗しても半端に入らない。

    最後に、追加した数とすでにあった数を1つの表で返す（SQL Editor は最後の
    結果だけを表示する）。NOT EXISTS は文の開始時点の表を見るので、両者の和は
    このファイルの問題数に一致する。
    """
    columns = ", ".join(COLUMNS)
    return (
        f"WITH v ({columns}) AS (VALUES\n"
        + ",\n".join(rows)
        + "\n),\nadded AS (\n"
        f"    INSERT INTO quiz_question ({columns}, correct_rate, answer_count, created_at)\n"
        f"    SELECT {', '.join('v.' + c for c in COLUMNS)}, 0, 0, now()\n"
        "    FROM v\n"
        "    WHERE NOT EXISTS (\n"
        "        SELECT 1 FROM quiz_question q\n"
        "        WHERE q.exam_type = v.exam_type\n"
        "          AND q.question_text = v.question_text\n"
        "          AND q.choices = v.choices)\n"
        "    RETURNING 1\n"
        ")\n"
        'SELECT (SELECT count(*) FROM added) AS "追加した問題",\n'
        '       (SELECT count(*) FROM v) - (SELECT count(*) FROM added) AS "すでにあった問題",\n'
        '       (SELECT count(*) FROM v) AS "このファイルの問題";\n'
    )


def statements(paths, chunk_bytes=CHUNK_BYTES):
    """バッチを読み、chunk_bytes 以下に分けた INSERT 文のリストを返す。"""
    from quiz.management.commands.import_questions import question_fields

    rows = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("question_sets"):
            raise SystemExit(f"{Path(path).name}: 四連問のセットは SQL での取り込みに対応していない")
        rows.extend(value_row(question_fields(q)) for q in payload["questions"])

    groups, current, size = [], [], 0
    for row in rows:
        n = len(row.encode("utf-8")) + 2
        if current and size + n > chunk_bytes:
            groups.append(current)
            current, size = [], 0
        current.append(row)
        size += n
    if current:
        groups.append(current)
    return [(len(group), insert_statement(group)) for group in groups]


def header(name, index, total, count, sources):
    lines = [
        f"-- 設問の取り込み（{name}、{index}/{total}本目、{count}問）。",
        f"-- 元のデータ: {', '.join(sources)}",
        "-- status は pending（審査待ち）で入り、人の医学的レビューで公開するまで学習者には出ない。",
        "-- 何度流しても結果は同じ（すでにある問題は入れない）。本数が複数あるときは全部流す。順番は問わない。",
        "-- 最後に「追加した問題／すでにあった問題」の表が出る。",
        "-- scripts/build_question_import_sql.py で作り直せる。",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="出力するファイル名の頭（scripts/sql/<name>_01.sql …）")
    parser.add_argument("batches", nargs="+", help="data/ にあるバッチのファイル名")
    parser.add_argument("--chunk-kb", type=int, default=CHUNK_BYTES // 1000)
    args = parser.parse_args()

    # 設問の変換に使うモデルの定数を読むためだけに Django を起動する。
    # DB にはつながず、サーバも立てないので、開発用の設定で足りる。
    os.environ.setdefault("DJANGO_DEBUG", "true")
    sys.path.insert(0, str(ROOT / "scripts"))
    from _django import setup_django

    setup_django()

    paths = [DATA_DIR / b for b in args.batches]
    for path in paths:
        if not path.exists():
            raise SystemExit(f"見つからない: {path}")
    chunks = statements(paths, args.chunk_kb * 1000)

    for old in OUT_DIR.glob(f"{args.name}_*.sql"):
        old.unlink()
    total = 0
    for i, (count, sql) in enumerate(chunks, start=1):
        out = OUT_DIR / f"{args.name}_{i:02d}.sql"
        out.write_text(header(args.name, i, len(chunks), count, args.batches) + sql, encoding="utf-8")
        total += count
        print(f"  {out.relative_to(ROOT)}  {count}問  {out.stat().st_size / 1000:.0f}KB")
    print(f"計 {total}問 / {len(chunks)}本")
    return 0


if __name__ == "__main__":
    sys.exit(main())
