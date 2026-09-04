#!/usr/bin/env python3
"""本番で本文が空になっている設問を、同梱データから復元するSQLを作る。

リポジトリの設問データ（backend/quiz/management/commands/data/*.json）には
question_text が空の設問は1問も無い。それでもアプリに「（本文なし）」が
出るということは、本番DBの行だけが壊れている。

frontend/src/components/QuestionPicker.jsx は
    q.case_stem || q.question_text || "（本文なし）"
と書いているので、この表示が出るのは本文も症例導入文も空のときだけ。

本文を空のまま保存できてしまう経路が実際にあった（AdminQuestionSerializer と
UserQuestionSerializer のどちらにも空チェックが無く、モデルが blank=True）。
そちらは別途ふさぐ。ここでは既に壊れている行を戻す。

どの行が壊れているか分からないので、全2,249問ぶんの復元値を持たせたうえで
「本文が空の行だけ」を対象にする。空でない行には当たらないので、全部流して
構わないし、何度流しても結果は同じ。

当て方は2段階:
  1. blueprint_code で当てる（国試。1問1コードで一意）
  2. 選択肢の並びを指紋にして当てる（CBT。blueprint_code が A-1 のような
     出題基準の項目コードで、1問1コードになっていない）

どちらでも当たらなかった行は最後に一覧で出す。選択肢まで壊れている行は
指紋が合わないのでここに残る。その場合は本文だけでは直せないので、
出力を見てから個別に対応する。

使い方:
    python scripts/build_question_text_repair.py --sql scripts/sql/repair_question_text.sql
"""

import argparse
import ast
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_GLOB = os.path.join(ROOT, "backend/quiz/management/commands/data/*.json")

# 本番DB上で選択肢から指紋を作る式。choices は JSONField（jsonb）で
# [{"key": "A", "text": "..."}, ...] の形。並び順も含めて1本の文字列にする。
# json 型で入っている環境でも動くよう ::jsonb を明示する。
FINGERPRINT_SQL = """(
      SELECT string_agg(e->>'key' || ':' || (e->>'text'), '|' ORDER BY ord)
      FROM jsonb_array_elements(q.choices::jsonb) WITH ORDINALITY AS t(e, ord)
    )"""

EMPTY_COND = "btrim(coalesce(q.question_text, '')) = ''"


def fingerprint(choices):
    """本番DBと同じ指紋を作る。

    同梱JSONは {"id","text"}、seed_demo と本番DBは {"key","text"}。
    取り込み時に id が key へ変換される（import_questions.convert_choices）
    ので、どちらの形でも同じ指紋になるようにする。
    """
    return "|".join(f"{c.get('id', c.get('key'))}:{c['text']}" for c in choices)


def load_seed_demo():
    """seed_demo.py のサンプル設問。

    本番にある本文が空の15行（CBT 10 / 国試 5）はこれ。SAMPLE_QUESTIONS に
    question_text が無く、seed_demo の defaults にも入っていなかったため、
    本文が空のまま作られていた。両方直したが、既に入っている行は
    get_or_create の defaults では更新されないので、ここから復元値を作る。

    blueprint_code を持たないので、当てられるのは選択肢の指紋だけ。

    seed_demo は先頭で Django を import するため、そのまま読み込むと落ちる。
    構文木から SAMPLE_QUESTIONS の定義だけを取り出す。
    """
    path = os.path.join(ROOT, "backend/quiz/management/commands/seed_demo.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    node = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
            getattr(t, "id", None) == "SAMPLE_QUESTIONS" for t in stmt.targets
        ):
            node = stmt.value
    if node is None:
        raise SystemExit("seed_demo.py に SAMPLE_QUESTIONS が無い")

    rows = []
    for item in node.elts:
        # dict(question_text=..., category=..., ...) の形だけを想定する。
        fields = {kw.arg: ast.literal_eval(kw.value) for kw in item.keywords}
        text = (fields.get("question_text") or "").strip()
        if not text:
            raise SystemExit(f"seed_demo の設問に question_text が無い: {fields.get('category')}")
        rows.append(
            {
                "code": "",
                "exam_type": fields["exam_type"],
                "fp": fingerprint(fields["choices"]),
                "text": text,
            }
        )
    return rows


def load_rows():
    """同梱データの全設問を (blueprint_code, exam_type, 指紋, 本文) で返す。"""
    rows = []
    for path in sorted(glob.glob(DATA_GLOB)):
        if ".report." in path:
            continue
        payload = json.load(open(path, encoding="utf-8"))
        items = list(payload.get("questions", []))
        # 連問は steps 側に本文がある。exam_type は親から借りる。
        for s in payload.get("question_sets", []) or []:
            for step in s.get("steps", []):
                step = dict(step)
                step.setdefault("exam_type", s.get("exam_type", "CBT"))
                step.setdefault("blueprint_code", s.get("blueprint_code", ""))
                items.append(step)
        for q in items:
            text = (q.get("question_text") or "").strip()
            if not text:
                raise SystemExit(f"同梱データ側が空: {path} {q.get('blueprint_code')}")
            rows.append(
                {
                    "code": (q.get("blueprint_code") or "").strip(),
                    "exam_type": q["exam_type"],
                    "fp": fingerprint(q["choices"]),
                    "text": text,
                }
            )
    return rows


def q(s):
    return "'" + s.replace("'", "''") + "'"


def by_code(rows):
    """blueprint_code が試験種別の中で一意なものだけを返す。

    CBT の blueprint_code は A-1 のような出題基準の項目コードで、
    953件が重複している。重複したコードで UPDATE すると別の設問の本文を
    書き込んでしまうので、一意なものだけに絞る。
    """
    count = {}
    for r in rows:
        if r["code"]:
            count[(r["exam_type"], r["code"])] = count.get((r["exam_type"], r["code"]), 0) + 1
    return [r for r in rows if r["code"] and count[(r["exam_type"], r["code"])] == 1]


def by_fingerprint(rows):
    """選択肢の指紋が全体で一意なものだけを返す。

    「下線部のうち誤っているのはどれか」型など、選択肢が 1〜5 の数字だけの
    設問は指紋が衝突する。衝突したものを当てにいくと取り違えるので外す。
    """
    count = {}
    for r in rows:
        count[r["fp"]] = count.get(r["fp"], 0) + 1
    return [r for r in rows if count[r["fp"]] == 1]


def write_sql(path, code_rows, fp_rows, part=None, totals=None):
    with open(path, "w", encoding="utf-8") as fh:
        if part:
            i, n = part
            fh.write(
                f"-- 本文が空になっている設問を同梱データから戻す（分割 {i}/{n}）。\n"
                f"-- Supabase の SQL Editor は1クエリ1MB前後が上限なので分けてある。\n"
                f"-- {n}本すべてを流す。順番は問わず、同じものを何度流してもよい。\n"
            )
        else:
            fh.write(
                "-- 本文が空になっている設問を同梱データから戻す（全問まとめ版）。\n"
                "-- psql で直接つなぐ場合はこちら:\n"
                '--   psql "$DATABASE_URL" -f scripts/sql/repair_question_text.sql\n'
                "-- SQL Editor から流すなら repair_question_text_01.sql 以降を使う。\n"
            )
        fh.write(
            "-- 対象は本文が空の行だけ。埋まっている行には当たらないので、\n"
            "-- 全部流して構わないし、何度流しても結果は同じ。\n"
            "BEGIN;\n\n"
        )

        if part in (None, (1, totals)):
            fh.write(
                "-- 直す前の件数。\n"
                "SELECT exam_type, count(*) AS 本文が空\n"
                "FROM quiz_question AS q\n"
                f"WHERE {EMPTY_COND}\n"
                "GROUP BY exam_type ORDER BY exam_type;\n\n"
            )

        if code_rows:
            fh.write(
                "-- (1) blueprint_code で当てる。国試は1問1コードで一意。\n"
                "UPDATE quiz_question AS q\nSET question_text = v.question_text\n"
                "FROM (VALUES\n"
            )
            fh.write(
                ",\n".join(
                    f"    ({q(r['code'])}, {q(r['exam_type'])}, {q(r['text'])})"
                    for r in code_rows
                )
            )
            fh.write(
                "\n) AS v(blueprint_code, exam_type, question_text)\n"
                "WHERE q.blueprint_code = v.blueprint_code\n"
                "  AND q.exam_type = v.exam_type\n"
                f"  AND {EMPTY_COND};\n\n"
            )

        if fp_rows:
            fh.write(
                "-- (2) 選択肢の並びを指紋にして当てる。CBT は blueprint_code が\n"
                "--     出題基準の項目コードで1問1コードになっていないため。\n"
                "--     本文が壊れていても選択肢は無事、という前提に立っている。\n"
                "WITH broken AS (\n"
                "  SELECT q.id, " + FINGERPRINT_SQL.strip() + " AS fp\n"
                "  FROM quiz_question AS q\n"
                f"  WHERE {EMPTY_COND}\n"
                ")\n"
                "UPDATE quiz_question AS q\nSET question_text = v.question_text\n"
                "FROM broken AS b, (VALUES\n"
            )
            fh.write(",\n".join(f"    ({q(r['fp'])}, {q(r['text'])})" for r in fp_rows))
            fh.write(
                "\n) AS v(fp, question_text)\n"
                "WHERE q.id = b.id AND b.fp = v.fp;\n\n"
            )

        if part in (None, (totals, totals)):
            fh.write(
                "-- 直したあとに残っているもの。0行なら完了。\n"
                "-- ここに残るのは選択肢まで壊れていて指紋が合わない行なので、\n"
                "-- 本文だけでは直せない。この出力を見て個別に対応する。\n"
                "SELECT q.id, q.exam_type, q.blueprint_code, q.category,\n"
                "       left(coalesce(q.explanation, ''), 40) AS 解説の冒頭\n"
                "FROM quiz_question AS q\n"
                f"WHERE {EMPTY_COND}\n"
                "ORDER BY q.exam_type, q.blueprint_code, q.id;\n\n"
            )

        fh.write("COMMIT;\n")


def split_by_size(rows, limit, key):
    """1本あたりが limit バイトを超えないように分ける。

    設問ごとに本文の長さが違うので、問数で切るとサイズがばらついて、
    余裕のあるファイルまで増えてしまう。実際の大きさで詰める。
    """
    groups, cur, cur_size = [], [], 0
    for r in rows:
        n = len(r["text"].encode()) + len(r[key].encode()) + 16
        if cur and cur_size + n > limit:
            groups.append(cur)
            cur, cur_size = [], 0
        cur.append(r)
        cur_size += n
    if cur:
        groups.append(cur)
    return groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", required=True, help="書き出し先")
    parser.add_argument(
        "--chunk-kb", type=int, default=500,
        help="分割SQL1本あたりの目安サイズ(KB)。0で分割しない",
    )
    args = parser.parse_args()

    rows = load_rows() + load_seed_demo()
    code_rows = by_code(rows)
    fp_rows = by_fingerprint(rows)

    covered = {id(r) for r in code_rows} | {id(r) for r in fp_rows}
    print(f"同梱データ {len(rows)}問")
    print(f"  blueprint_code で当てられる  {len(code_rows):5d}問")
    print(f"  選択肢の指紋で当てられる      {len(fp_rows):5d}問")
    print(f"  どちらかで当てられる          {len(covered):5d}問")
    uncovered = [r for r in rows if id(r) not in covered]
    if uncovered:
        print(f"  ★どちらでも当てられない      {len(uncovered):5d}問")
        for r in uncovered[:5]:
            print(f"      {r['exam_type']} {r['code'] or '(コード無し)'}: {r['text'][:40]}")

    write_sql(args.sql, code_rows, fp_rows)
    print(f"  SQL: {args.sql} ({os.path.getsize(args.sql) / 1024:.0f}KB)")

    if args.chunk_kb > 0:
        stem, ext = os.path.splitext(args.sql)
        # 1本の中に (1) と (2) の両方が入るので、それぞれ半分ずつを上限にする。
        half = args.chunk_kb * 1024 // 2
        cg = split_by_size(code_rows, half, key="code")
        fg = split_by_size(fp_rows, half, key="fp")
        n = max(len(cg), len(fg))
        for i in range(n):
            path = f"{stem}_{i + 1:02d}{ext}"
            write_sql(
                path,
                cg[i] if i < len(cg) else [],
                fg[i] if i < len(fg) else [],
                part=(i + 1, n),
                totals=n,
            )
            print(f"    分割 {i + 1}/{n}: {os.path.basename(path)} "
                  f"({os.path.getsize(path) / 1024:.0f}KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
