#!/usr/bin/env python3
"""問題数の薄い科目を埋めるCBT設問を、取り込み用のバッチJSONにまとめる。

    python scripts/build_cbt_gap_batch.py \
        --out backend/quiz/management/commands/data/cbt_batch_gap_2026.json

書き出したら scripts/validate_questions.py で検査する。取り込みは
import_questions が status=pending / source=llm で入れるので、公開には
人の医学的レビューが要る。
"""

import argparse
import collections
import importlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# 追加する科目のモジュール。増やすときはここに足す。
MODULES = [
    "cbt_gap_questions.pediatrics",
    "cbt_gap_questions.immunology",
    "cbt_gap_questions.musculoskeletal",
    "cbt_gap_questions.psychiatry",
    "cbt_gap_questions.endocrine",
    "cbt_gap_questions.infection",
]

# 日本語入力の変換ミスでキリル文字などが紛れる。見た目で気づけないので
# 機械で弾く（実際に「клинический」を書き込んでしまった）。
FOREIGN_SCRIPT = re.compile(r"[Ѐ-ԯ가-힯฀-๿]")


def collect():
    out = []
    for name in MODULES:
        module = importlib.import_module(name)
        out.extend(module.QUESTIONS)
    return out


def check(items):
    """書き出す前の自己点検。validate_questions.py と重ならない部分を見る。"""
    problems = []
    for item in items:
        code = item["id"]
        # disease も見る。表示には出ないが、ここに紛れたものを見逃すと
        # 次に使うときまで残る（実際に4件書き込んでしまった）。
        blob = (
            item["question_text"]
            + item["disease"]
            + "".join(c["text"] for c in item["choices"])
            + item["explanation"]
            + "".join(item.get("distractor_rationale", {}).values())
        )
        found = FOREIGN_SCRIPT.findall(blob)
        if found:
            problems.append(f"{code}: 想定外の文字 {sorted(set(found))}")

        # 誤答理由は正答以外の4つぶんそろえる。抜けていると画面で空欄になる。
        want = {c["id"] for c in item["choices"]} - {item["correct_choice_id"]}
        got = set(item.get("distractor_rationale", {}))
        if got != want:
            problems.append(f"{code}: 誤答理由が {sorted(got)}（{sorted(want)}が必要）")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    questions = collect()
    # 正答の位置を A〜E に順番に割り当てる。科目ごとにまとめて書くと
    # 位置が偏るので、通し番号で機械的に散らす。
    items = [
        q.to_json(f"gap2026-{i:03d}", target_key="ABCDE"[(i - 1) % 5])
        for i, q in enumerate(questions, 1)
    ]

    problems = check(items)
    if problems:
        for p in problems:
            print(f"  ★ {p}")
        raise SystemExit(f"{len(problems)}件の問題があるので書き出さない")

    by_cat = collections.Counter(i["category"] for i in items)
    keys = collections.Counter(i["correct_choice_id"] for i in items)
    longest = sum(
        1
        for i in items
        if len(next(c["text"] for c in i["choices"] if c["id"] == i["correct_choice_id"]))
        >= max(len(c["text"]) for c in i["choices"])
    )

    print(f"設問 {len(items)}問")
    for cat, n in by_cat.most_common():
        print(f"  {n:4d}  {cat}")
    print("  正答キーの分布: " + " ".join(
        f"{k}={keys.get(k,0)}({keys.get(k,0)/len(items):.0%})" for k in "ABCDE"))
    print(f"  正答が最長の選択肢: {longest}/{len(items)} ({longest/len(items):.0%}、40%未満が目安)")

    payload = {
        "meta": {
            "generated_at": "2026-09-01",
            "generator": "llm-authored-editorial",
            "blueprint_version": "CBT-model-core-curriculum",
            "batch_id": "gap2026",
        },
        "questions": items,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
