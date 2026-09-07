#!/usr/bin/env python3
"""連問の取り込みで増えた設問を、同梱データへ足す。

import_kokushi.py を回し直すと解説が取り込み当初の定型文に戻り、手で直した
本文（第117回D41の第XIII因子、第118回F45の判定基準表、第119回C44など）も
上書きされてしまう。増えたのは連問だけなので、既存の設問には一切触らず、
blueprint_code が新しいものだけを足す。

    python scripts/merge_kokushi_series.py --new-dir /tmp        # 差分を見る
    python scripts/merge_kokushi_series.py --new-dir /tmp --write
"""

import argparse
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backend/quiz/management/commands/data")
EXAMS = (114, 115, 116, 117, 118, 119)


def _checks():
    """同梱データの品質検査を、そのまま通過フィルタとして借りる。

    連問の症例文はこれまで一度も取り込んでいなかったので、既存の設問が
    通ってきた検査を受けていない。実際に「下s浮腫」（下腿浮腫の化け）や
    「(2 )0」（括弧と数字の入れ替わり）が混じっていた。検査を二重に書くと
    片方だけ直して食い違うので、テストが持っている定義をそのまま使う。
    """
    path = os.path.join(ROOT, "backend/tests/test_shipped_data.py")
    spec = importlib.util.spec_from_file_location("shipped_checks", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return [
        ("字化け", m.GLYPH_CORRUPTION),
        ("外国語の混入", m.FOREIGN_SCRIPT),
        ("落ちた数字", m.DROPPED_NUMBER),
        ("数字と漢字の入れ替わり", m.KANJI_DIGIT_KANJI),
        ("数字のあとの体表用語", m.BODY_KANJI_AFTER_DIGIT),
        ("部位のあとの欧字", m.POSITION_KANJI_THEN_LATIN),
        ("括弧に似た字", m.BRACKET_LOOKALIKE),
        ("語頭の脱落", m.DROPPED_WORD_HEAD),
        ("列区切りの残り", m.STRAY_SEPARATOR),
        ("制御文字", m.UNUSABLE),
    ]


def rejected_reason(question, checks):
    """設問を落とす理由。通るなら None。"""
    texts = [question["question_text"]] + [c["text"] for c in question["choices"]]
    for text in texts:
        for name, pat in checks:
            if pat.search(text):
                return name
    # 括弧の対応。開きと閉じの数が合わないものは切り出しに失敗している。
    for text in texts:
        for opening, closing in (("(", ")"), ("（", "）"), ("「", "」"), ("〈", "〉")):
            if text.count(opening) != text.count(closing):
                return f"括弧の対応（{opening}{closing}）"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-dir", required=True, help="取り込み直した kNNN.json の場所")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    checks = _checks()
    total_added = 0
    for exam in EXAMS:
        cur_path = os.path.join(DATA, f"kokushi_{exam}.json")
        new_path = os.path.join(args.new_dir, f"k{exam}.json")
        if not os.path.exists(new_path):
            print(f"  第{exam}回: {new_path} が無いので飛ばす")
            continue

        cur = json.load(open(cur_path, encoding="utf-8"))
        new = json.load(open(new_path, encoding="utf-8"))
        have = {q["blueprint_code"] for q in cur["questions"]}
        candidates = [q for q in new["questions"] if q["blueprint_code"] not in have]
        added, dropped = [], {}
        for q in candidates:
            why = rejected_reason(q, checks)
            if why:
                dropped[why] = dropped.get(why, 0) + 1
            else:
                added.append(q)

        # 取り込み直しで消えた設問がないかを見る。既存を触らない方針なので
        # 消えはしないが、抽出が悪化していたら気づけるようにしておく。
        lost = have - {q["blueprint_code"] for q in new["questions"]}

        cur["questions"].extend(added)
        cur["questions"].sort(key=_sort_key)
        total_added += len(added)
        note = f"  ※新側に無い既存 {len(lost)}問" if lost else ""
        drop_note = ("  落とした: " + ", ".join(f"{k}{v}" for k, v in sorted(dropped.items()))
                     if dropped else "")
        print(f"  第{exam}回: {len(have)} -> {len(cur['questions'])}問 "
              f"(+{len(added)}){note}{drop_note}")

        if args.write and added:
            with open(cur_path, "w", encoding="utf-8") as fh:
                json.dump(cur, fh, ensure_ascii=False, indent=2)
                fh.write("\n")

    print(f"  合計 +{total_added}問" + ("（書き込み済み）" if args.write else "（下見のみ）"))
    return 0


def _sort_key(q):
    """ブロック記号→設問番号の順。番号は数値で比べる（文字列だと10が2より前）。"""
    parts = q["blueprint_code"].split("-")
    if len(parts) != 3:
        return ("", 0)
    return (parts[1], int(parts[2]) if parts[2].isdigit() else 0)


if __name__ == "__main__":
    sys.exit(main())
