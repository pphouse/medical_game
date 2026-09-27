#!/usr/bin/env python3
"""同梱データの分野名を quiz/categories.py の規則で引き直す。

科目立てを変えたら、同梱データ側もそれに合わせないと
tests/test_questions.py の検証（バリデータ）が落ちる。手で直すと取りこぼす
ので機械で当て直す。

取り込み時と同じ引数で normalize() を呼ぶので、ここで書いた結果と
import_questions が決める分野は一致する。

    python scripts/apply_categories.py            # 差分を見るだけ
    python scripts/apply_categories.py --write    # 書き込む
    python scripts/apply_categories.py --sql out.sql  # 本番用SQL
"""

import argparse
import collections
import glob
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_GLOB = os.path.join(ROOT, "backend/quiz/management/commands/data/*.json")

spec = importlib.util.spec_from_file_location(
    "cats", os.path.join(ROOT, "backend/quiz/categories.py")
)
cats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cats)


def text_for(item, parent=None):
    """分野の推定に使う本文。import_questions と同じ組み立て方にする。"""
    parts = []
    if parent:
        parts.append(parent.get("case_stem", ""))
    parts.append(item.get("question_text", ""))
    parts.append((parent or item).get("disease", item.get("topic", "")))
    parts += [c["text"] for c in item.get("choices", [])]
    return "\n".join(p for p in parts if p)


def walk(payload):
    """(設問, 分野の持ち主, 親の連問) を返す。連問は分野が親側にある。"""
    for q in payload.get("questions", []):
        yield q, q, None
    for s in payload.get("question_sets", []) or []:
        for step in s.get("steps", []):
            yield step, s, s


def baseline(path):
    """git の HEAD 時点の同梱データ。本番DBの分野はこちらに対応する。"""
    rel = os.path.relpath(path, ROOT)
    out = subprocess.run(
        ["git", "-C", ROOT, "show", f"HEAD:{rel}"], capture_output=True, text=True
    )
    if out.returncode != 0:
        raise SystemExit(f"git から読めない: {rel}")
    return json.loads(out.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--sql")
    args = parser.parse_args()
    if args.write and args.sql:
        raise SystemExit(
            "--write と --sql は分けて実行する。SQL の基準は git の HEAD で、"
            "先に書き込むと差分が消えるため。"
        )

    moves = collections.Counter()
    # 本番用: (試験種別, 旧分野, 新分野) と、個別に動く設問の手掛かり
    per_question = []
    changed_files = {}

    for path in sorted(glob.glob(DATA_GLOB)):
        if ".report." in path:
            continue
        # SQL は本番へ当てるものなので、基準は「まだ引き直していない状態」＝
        # git の HEAD にする。作業ツリーを先に --write してしまうと差分が
        # 消えて空のSQLが出る（実際に一度そうなった）。
        payload = baseline(path) if args.sql and not args.write else json.load(
            open(path, encoding="utf-8")
        )
        touched = 0
        for item, owner, parent in walk(payload):
            exam = owner.get("exam_type", "CBT")
            old = owner.get("category", "")
            new = cats.normalize(
                old, text_for(item, parent), owner.get("blueprint_code", ""), exam
            )
            if new == old:
                continue
            moves[(exam, old, new)] += 1
            per_question.append(
                {
                    "exam": exam,
                    "old": old,
                    "new": new,
                    "code": owner.get("blueprint_code", ""),
                    "fp": "|".join(
                        f"{c['id']}:{c['text']}" for c in item.get("choices", [])
                    ),
                }
            )
            owner["category"] = new
            touched += 1
        if touched:
            changed_files[path] = (payload, touched)

    total = sum(moves.values())
    print(f"分野が変わる設問 {total}問")
    for (exam, a, b), n in moves.most_common():
        print(f"  {n:4d}  {exam:8s} {a}  ->  {b}")

    if args.write:
        for path, (payload, touched) in changed_files.items():
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print(f"  書き込み: {os.path.basename(path)} ({touched}問)")

    if args.sql:
        write_sql(args.sql, moves, per_question)
        print(f"  SQL: {args.sql} ({os.path.getsize(args.sql) / 1024:.0f}KB)")

    return 0


def lit(s):
    return "'" + s.replace("'", "''") + "'"


def write_sql(path, moves, per_question):
    """本番の分野を揃えるSQL。

    2つに分かれる。
      1. 科目そのものの統合（救急/中毒/麻酔科 -> 救急・中毒・麻酔）。
         旧名の行をまとめて書き換えるだけなので設問を特定する必要がない。
      2. 個々の設問の付け替え（感染症・放射線科）。国試は blueprint_code、
         CBT は選択肢の指紋で当てる。CBT の blueprint_code は出題基準の
         項目コードで1問1コードになっていないため。
    """
    renames = {
        "救急": "救急・中毒・麻酔",
        "中毒": "救急・中毒・麻酔",
        "麻酔科": "救急・中毒・麻酔",
        "中毒・環境": "救急・中毒・麻酔",
    }
    individual = [p for p in per_question if p["old"] not in renames]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "-- 本番の分野名を新しい科目立てに揃える。何度流しても結果は同じ。\n"
            "BEGIN;\n\n"
            "-- (1) 救急・中毒・麻酔科を1科目に統合する。\n"
            "UPDATE quiz_question SET category = '救急・中毒・麻酔'\n"
            "WHERE category IN ("
            + ", ".join(lit(k) for k in renames)
            + ");\n\n"
        )
        # QuestionSet に category 列は無い（連問の分野は子の Question 側だけが
        # 持つ）。JSON の question_sets[].category は取り込み時に子へ配るための
        # もので、DBには載らない。

        koku = [p for p in individual if p["exam"] == "KOKUSHI" and p["code"]]
        if koku:
            fh.write(
                "-- (2a) 国試: blueprint_code で当てる。\n"
                "UPDATE quiz_question AS q SET category = v.category\n"
                "FROM (VALUES\n"
                + ",\n".join(f"    ({lit(p['code'])}, {lit(p['new'])})" for p in koku)
                + "\n) AS v(blueprint_code, category)\n"
                "WHERE q.blueprint_code = v.blueprint_code\n"
                "  AND q.exam_type = 'KOKUSHI';\n\n"
            )

        cbt = [p for p in individual if p["exam"] != "KOKUSHI" and p["fp"]]
        if cbt:
            fh.write(
                "-- (2b) CBT: 選択肢の並びを指紋にして当てる。\n"
                "WITH target AS (\n"
                "  SELECT q.id, (\n"
                "    SELECT string_agg(e->>'key' || ':' || (e->>'text'), '|' ORDER BY ord)\n"
                "    FROM jsonb_array_elements(q.choices::jsonb) WITH ORDINALITY AS t(e, ord)\n"
                "  ) AS fp\n"
                "  FROM quiz_question AS q WHERE q.exam_type <> 'KOKUSHI'\n"
                ")\n"
                "UPDATE quiz_question AS q SET category = v.category\n"
                "FROM target AS b, (VALUES\n"
                + ",\n".join(f"    ({lit(p['fp'])}, {lit(p['new'])})" for p in cbt)
                + "\n) AS v(fp, category)\n"
                "WHERE q.id = b.id AND b.fp = v.fp;\n\n"
            )

        fh.write(
            "-- 統合前の科目名が残っていないことの確認。0行なら完了。\n"
            "SELECT category, count(*) FROM quiz_question\n"
            "WHERE category IN ("
            + ", ".join(lit(k) for k in renames)
            + ")\nGROUP BY category;\n\n"
            "-- 科目別の問題数。\n"
            "SELECT exam_type, category, count(*) FROM quiz_question\n"
            "GROUP BY exam_type, category ORDER BY exam_type, count(*) DESC;\n\n"
            "COMMIT;\n"
        )


if __name__ == "__main__":
    sys.exit(main())
