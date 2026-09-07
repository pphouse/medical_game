"""連問など、解説が「準備中」のまま残っている国試設問に解説を書き入れる。

解説の書式は既に入っている1,147問と揃える。手で書くのは「なぜ正しいか」
「なぜ誤りか」だけで、正答の記号・選択肢の文言・出典表記はデータから
機械的に組み立てる（書き写すとデータとずれたときに気づけないため）。

    正答は B「血糖測定」。

    <本文>

    【誤答選択肢の解説】
    A「脳波」: <理由>
    ...

    ※この解説はアプリ編集部が作成したものです。…

    出典：厚生労働省ホームページ 第114回医師国家試験 B043（URL）／…

使い方:

    from scripts.fill_explanations import fill
    fill("kokushi_114", {"114-B-43": ("本文", {"A": "理由", ...})})
"""

import json
import pathlib
import re

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "backend/quiz/management/commands/data"

HEADING = "【誤答選択肢の解説】"
DISCLAIMER = (
    "※この解説はアプリ編集部が作成したものです。"
    "厚生労働省が公表する過去問には解説は含まれません。"
)
# 日本語・英数字・記号以外（キリル文字やハングルの混入）を弾く。
FOREIGN = re.compile(r"[Ѐ-ӿ가-힯฀-๿]")


def _source_line(old):
    """既存の解説から出典表記を組み立て直す（回とコードとURLを引き継ぐ）。"""
    head = re.search(r"^出典：[^\n（(]*", old, re.M)
    url = re.search(r"https?://\S+", old)
    if not head:
        raise ValueError("出典行が見つからない")
    line = head.group(0).rstrip()
    if url:
        line += f"（{url.group(0)}）"
    return line + "／設問文および選択肢を本アプリの表示形式に整形"


def fill(stem, entries):
    """entries: {blueprint_code: (本文, {選択肢キー: 理由})}"""
    path = DATA_DIR / f"{stem}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("questions", data) if isinstance(data, dict) else data
    by_code = {q.get("blueprint_code"): q for q in items if isinstance(q, dict)}

    for code, (body, rationales) in entries.items():
        q = by_code.get(code)
        if q is None:
            raise KeyError(f"{code} が {stem}.json に無い")
        if "準備中" not in (q.get("explanation") or ""):
            raise ValueError(f"{code} は既に解説がある。上書きしない。")

        answer = q["correct_choice_id"]
        choices = {c["id"]: c["text"] for c in q["choices"]}
        expected = set(choices) - {answer}
        if set(rationales) != expected:
            raise ValueError(
                f"{code}: 誤答の集合が合わない。"
                f"要 {sorted(expected)} / 来 {sorted(rationales)}"
            )
        for text in [body, *rationales.values()]:
            if FOREIGN.search(text):
                raise ValueError(f"{code}: 日本語以外の文字が混ざっている: {text[:40]}")
            if "準備中" in text:
                raise ValueError(f"{code}: プレースホルダのまま")

        lines = [f"{k}「{choices[k]}」: {rationales[k]}" for k in sorted(rationales)]
        q["explanation"] = (
            f"正答は {answer}「{choices[answer]}」。\n\n"
            f"{body}\n\n"
            f"{HEADING}\n" + "\n".join(lines) + "\n\n"
            f"{DISCLAIMER}\n\n"
            f"{_source_line(q['explanation'])}"
        )

    if isinstance(data, dict):
        data["questions"] = items
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(entries)
