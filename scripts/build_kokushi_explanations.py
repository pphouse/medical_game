#!/usr/bin/env python3
"""国試の解説を組み立てる。

scripts/kokushi_explanations/*.json に書いた解説の本体（point と誤答理由）を、
設問データ（backend/quiz/management/commands/data/kokushi_*.json）と突き合わせて
表示用の1本の文字列にする。

手で書くのは「なぜその選択肢が正しい／誤りか」だけにして、正答の記号・選択肢の
文言・出典表記は設問データから機械的に付ける。書き写すとデータとずれたときに
気づけないため。

出典表記について: 厚生労働省の Public Data License 1.0 が及ぶのは設問文と
選択肢であって、ここで書く解説は及ばない。解説を出典の一部に見せてしまうと
出所を偽ることになるので、段落を分けてアプリ作成であることを明記する。

使い方:
    python scripts/build_kokushi_explanations.py              # 検証のみ
    python scripts/build_kokushi_explanations.py --write      # 設問JSONに反映
    python scripts/build_kokushi_explanations.py --sql out.sql  # 本番用SQL
"""

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_GLOB = os.path.join(ROOT, "backend/quiz/management/commands/data/kokushi_*.json")
EXPL_DIR = os.path.join(ROOT, "scripts/kokushi_explanations")

DISCLAIMER = (
    "※この解説はアプリ編集部が作成したものです。"
    "厚生労働省が公表する過去問には解説は含まれません。"
)
PLACEHOLDER_MARK = "詳しい解説は準備中"

# 日本語入力の変換ミスでキリル文字やハングルが紛れることがある（実際に
# 「交感神経актив」を作り込んだ）。見た目が似ていて目視では気づけないので
# 機械で弾く。ギリシャ文字は β2刺激薬・α遮断薬などで正当に使うため除く。
FOREIGN_SCRIPT = re.compile(r"[\u0400-\u052F\uAC00-\uD7AF\u0E00-\u0E7F]")


def load_questions():
    """blueprint_code -> 設問 の索引。"""
    index = {}
    for path in sorted(glob.glob(DATA_GLOB)):
        if ".report." in path:
            continue
        payload = json.load(open(path, encoding="utf-8"))
        for q in payload["questions"]:
            index[q["blueprint_code"]] = (path, q)
    return index


def load_authored():
    authored = {}
    for path in sorted(glob.glob(os.path.join(EXPL_DIR, "*.json"))):
        for code, body in json.load(open(path, encoding="utf-8")).items():
            if code in authored:
                raise SystemExit(f"解説が重複している: {code}")
            authored[code] = body
    return authored


def check_text(code, field, text):
    found = FOREIGN_SCRIPT.findall(text)
    if found:
        raise SystemExit(f"{code} の {field} に想定外の文字: {sorted(set(found))}")
    if not text.strip():
        raise SystemExit(f"{code} の {field} が空")


def compose(question, body):
    """表示用の解説文を組み立てる。"""
    choices = {c["id"]: c["text"] for c in question["choices"]}
    key = question["correct_choice_id"]
    if key not in choices:
        raise SystemExit(f"{question['blueprint_code']}: 正答 {key} が選択肢に無い")

    code = question["blueprint_code"]
    check_text(code, "point", body.get("point", ""))
    for k, v in (body.get("distractors") or {}).items():
        check_text(code, f"distractors[{k}]", v)

    parts = [f"正答は {key}「{choices[key]}」。", "", body["point"].strip()]

    wrong = {k: v for k, v in (body.get("distractors") or {}).items() if k != key}
    unknown = set(wrong) - set(choices)
    if unknown:
        raise SystemExit(f"{question['blueprint_code']}: 存在しない選択肢 {sorted(unknown)}")
    if wrong:
        parts += ["", "【誤答選択肢の解説】"]
        parts += [f"{k}「{choices[k]}」: {wrong[k].strip()}" for k in sorted(wrong)]

    parts += ["", DISCLAIMER, "", question["source_note"]]
    return "\n".join(parts)


def write_sql(path, codes, composed, part=None):
    """UPDATE 文を1ファイル書き出す。

    Supabase の SQL Editor には1クエリあたりのサイズ上限（1MB前後）があり、
    全1,147問を1本にすると "Query is too large to be run via the SQL Editor" で
    弾かれる。psql で直接つなぐなら1本で通るので、分割版と併せて両方作る。
    どのファイルも単独で完結していて、順不同・何度流しても結果は同じ。
    """
    if part:
        i, n = part
        head = (
            f"-- 国試の解説を差し替える（分割 {i}/{n}）。\n"
            f"-- Supabase の SQL Editor は1クエリ1MB前後が上限なので分けてある。\n"
            f"-- {n}本すべてを流す。順番は問わず、同じものを何度流してもよい。\n"
        )
    else:
        head = (
            "-- 国試の解説を差し替える（全問まとめ版）。\n"
            "-- 1.4MB あるので Supabase の SQL Editor では大きすぎて弾かれる。\n"
            "-- psql で直接つなぐ場合はこちらを使う:\n"
            "--   psql \"$DATABASE_URL\" -f scripts/sql/kokushi_explanations.sql\n"
            "-- SQL Editor から流すなら kokushi_explanations_01.sql 以降を使う。\n"
        )

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            head
            + "-- blueprint_code で行を特定するので、本文が壊れている行でも当たる。\n"
            "BEGIN;\n\nUPDATE quiz_question AS q\nSET explanation = v.explanation\n"
            "FROM (VALUES\n"
        )
        rows = []
        for code in codes:
            text = composed[code].replace("'", "''")
            rows.append(f"    ('{code}', '{text}')")
        fh.write(",\n".join(rows))
        fh.write(
            "\n) AS v(blueprint_code, explanation)\n"
            "WHERE q.blueprint_code = v.blueprint_code\n"
            "  AND q.exam_type = 'KOKUSHI';\n\n"
            "-- 残りのプレースホルダ件数。最後の1本まで流し終えると0になる。\n"
            "SELECT count(*) AS remaining_placeholders\n"
            f"FROM quiz_question WHERE explanation LIKE '%{PLACEHOLDER_MARK}%';\n\n"
            "COMMIT;\n"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="設問JSONの explanation を書き換える")
    parser.add_argument("--sql", help="本番反映用のSQLを書き出す")
    parser.add_argument("--chunk", type=int, default=250,
                        help="分割SQLの1ファイルあたりの問数。0で分割しない")
    args = parser.parse_args()

    questions = load_questions()
    authored = load_authored()

    orphans = sorted(set(authored) - set(questions))
    if orphans:
        raise SystemExit(f"設問が見つからない解説: {orphans[:10]}")

    composed = {}
    for code, body in authored.items():
        _, question = questions[code]
        composed[code] = compose(question, body)

    done = len(composed)
    total = len(questions)
    print(f"解説あり {done} / {total}問  (残り {total - done})")
    per = {}
    for code in questions:
        exam = code.split("-")[0]
        got, tot = per.get(exam, (0, 0))
        per[exam] = (got + (1 if code in composed else 0), tot + 1)
    for exam in sorted(per):
        got, tot = per[exam]
        mark = " 完了" if got == tot else ""
        print(f"  第{exam}回  {got:4d} / {tot:4d}{mark}")

    if args.write:
        by_path = {}
        for code, text in composed.items():
            path, _ = questions[code]
            by_path.setdefault(path, {})[code] = text
        for path, mapping in by_path.items():
            payload = json.load(open(path, encoding="utf-8"))
            for q in payload["questions"]:
                if q["blueprint_code"] in mapping:
                    q["explanation"] = mapping[q["blueprint_code"]]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print(f"  書き込み: {os.path.basename(path)} ({len(mapping)}問)")

    if args.sql:
        codes = sorted(composed)
        write_sql(args.sql, codes, composed)
        size = os.path.getsize(args.sql)
        print(f"  SQL: {args.sql} ({len(codes)}問, {size / 1024:.0f}KB)")

        if args.chunk > 0 and len(codes) > args.chunk:
            stem, ext = os.path.splitext(args.sql)
            groups = [codes[i : i + args.chunk] for i in range(0, len(codes), args.chunk)]
            for i, group in enumerate(groups, start=1):
                path = f"{stem}_{i:02d}{ext}"
                write_sql(path, group, composed, part=(i, len(groups)))
                size = os.path.getsize(path)
                print(f"    分割 {i}/{len(groups)}: {os.path.basename(path)} "
                      f"({len(group)}問, {size / 1024:.0f}KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
