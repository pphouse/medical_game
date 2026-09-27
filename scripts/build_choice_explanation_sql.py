#!/usr/bin/env python3
"""本番の国試の解説を、選択肢ごとに分けた形へ移す SQL を書き出す。

quiz.0010_backfill_choice_explanations と同じことを SQL でやる。移行の
中身（どこで切るか）は Python 側の split_choice_explanations が決めており、
SQL で正規表現を組み直すと定義が二重になるので、**同梱データから取り込みと
同じ変換を通した結果**を値として並べる。データが唯一の出所になる。

kokushi_explanations.sql（解説を入れるだけ・explanation 列のみ）を置き換える。
あちらは 9/4 時点の文面で、その後に直した4問が古いままになっている。

使い方:
    python scripts/build_choice_explanation_sql.py
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from quiz.choice_explanations import split_choice_explanations  # noqa: E402
from quiz.explanations import strip_boilerplate  # noqa: E402

DATA_GLOB = os.path.join(ROOT, "backend/quiz/management/commands/data/kokushi_*.json")
OUT_DIR = os.path.join(ROOT, "scripts/sql")
CHUNK_BYTES = 400_000

HEADER = """\
-- 国試の解説を、選択肢ごとに分けた形で入れ直す。何度流しても結果は同じ。
--
-- 先に scripts/sql/migrate_quiz_0009_choice_explanations.sql を流すこと
-- （choice_explanations 列がまだ無いとここで落ちる）。
--
-- 中身は同梱データ（backend/quiz/management/commands/data/kokushi_*.json）から
-- 取り込みと同じ変換（import_questions.build_explanation）を通して生成した。
-- scripts/build_choice_explanation_sql.py で作り直せる。
--
-- kokushi_explanations.sql の後継。あちらは explanation 列だけを更新し、
-- 文面も 9/4 時点のもの（否定形を読み違えた3問を含む）。こちらを流せば
-- 直った文面に揃う。
--
-- 連問116問は本番にまだ入っていないので当たらない（0行更新）。
-- import_questions 経由で解説ごと入る。
"""

FOOTER = """\
-- quiz.0010_backfill_choice_explanations を記録する。中身は上の UPDATE で
-- 済ませてあるので、あとから manage.py migrate を通しても二重には当たらない。
INSERT INTO django_migrations (app, name, applied)
SELECT 'quiz', '0010_backfill_choice_explanations', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM django_migrations
    WHERE app = 'quiz' AND name = '0010_backfill_choice_explanations'
);

-- 確認: 公開中の国試で、まだ本文に畳み込まれたまま（列が空）の数。0であること。
SELECT count(*) AS folded_not_split
FROM quiz_question
WHERE exam_type = 'KOKUSHI' AND status = 'published'
  AND explanation LIKE '%【誤答選択肢の解説】%'
  AND choice_explanations = '{}'::jsonb;
"""


def q(s):
    return "'" + s.replace("'", "''") + "'"


def build(item):
    explanation = strip_boilerplate(item["explanation"])
    explanation, folded = split_choice_explanations(explanation)
    per = {
        str(k).strip().upper(): str(v).strip()
        for k, v in (item.get("distractor_rationale") or {}).items()
        if str(v).strip()
    }
    return explanation, {**folded, **per}


def main():
    rows = []
    for path in sorted(glob.glob(DATA_GLOB)):
        if ".report." in path:
            continue
        for item in json.load(open(path, encoding="utf-8"))["questions"]:
            code = item["blueprint_code"]
            answer = item["correct_choice_id"]
            keys = {c["id"] for c in item["choices"]}
            body, per = build(item)
            text = next(c["text"] for c in item["choices"] if c["id"] == answer)
            # データとずれた解説を本番へ流さない。取り込み時と同じ不変条件。
            assert set(per) == keys - {answer}, f"{code}: 誤答解説の集合がずれている"
            assert answer not in per, f"{code}: 正答が誤答解説に入っている"
            assert "【誤答選択肢の解説】" not in body, f"{code}: 見出しが本文に残っている"
            assert "出典：厚生労働省" in body, f"{code}: 出典が落ちている"
            assert body.startswith(f"正答は {answer}「{text}」"), f"{code}: 正答引用がずれている"
            rows.append(
                f"    ({q(code)}, {q(body)},\n     {q(json.dumps(per, ensure_ascii=False))})"
            )

    stmt_head = (
        "UPDATE quiz_question AS q\n"
        "SET explanation = v.explanation,\n"
        "    choice_explanations = v.choice_explanations::jsonb\n"
        "FROM (VALUES\n"
    )
    stmt_tail = "\n) AS v(blueprint_code, explanation, choice_explanations)\nWHERE q.exam_type = 'KOKUSHI' AND q.blueprint_code = v.blueprint_code;\n"

    def statement(chunk):
        return stmt_head + ",\n".join(chunk) + stmt_tail

    whole = os.path.join(OUT_DIR, "kokushi_choice_explanations.sql")
    with open(whole, "w", encoding="utf-8") as f:
        f.write(HEADER + "\nBEGIN;\n\n" + statement(rows) + "\n" + FOOTER + "\nCOMMIT;\n")

    # SQL Editor 用に分ける。1ファイルずつ独立して流せる形にする。
    chunks, current, size = [], [], 0
    for row in rows:
        if size + len(row.encode()) > CHUNK_BYTES and current:
            chunks.append(current)
            current, size = [], 0
        current.append(row)
        size += len(row.encode())
    if current:
        chunks.append(current)

    for i, chunk in enumerate(chunks, 1):
        part = os.path.join(OUT_DIR, f"kokushi_choice_explanations_{i:02d}.sql")
        last = i == len(chunks)
        with open(part, "w", encoding="utf-8") as f:
            f.write(
                f"-- {i}/{len(chunks)}。番号順に流す。"
                + ("最後のこれで記録まで入る。\n" if last else "\n")
                + "-- 先に migrate_quiz_0009_choice_explanations.sql を流すこと。\n"
                + "\nBEGIN;\n\n"
                + statement(chunk)
                + ("\n" + FOOTER if last else "")
                + "\nCOMMIT;\n"
            )
        print(f"{os.path.basename(part)}: {len(chunk)}問")

    print(f"\n{whole} に {len(rows)}問（{len(chunks)}分割）")


if __name__ == "__main__":
    main()
