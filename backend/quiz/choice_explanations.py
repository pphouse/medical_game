"""選択肢ごとの解説を、解説本文から切り出して構造化する。

取り込みバッチは選択肢ごとの解説を ``distractor_rationale`` で持っているが、
これまでは解説本文の末尾に

    【誤答選択肢の解説】
    B: 前壁中隔梗塞はV1〜V4のST上昇を示し…
    C: 側壁梗塞はI・aVL・V5・V6のST上昇を示す。

と文字列で畳んで保存していた。選択肢の横に並べて表示したいので、
``Question.choice_explanations``（{"B": "…"} 形式）へ移す。

本文の末尾に固まっている前提で切り出す。「A:」で始まる行が本文中にたまたま
現れても拾わないよう、見出し（BLOCK_HEADING）より後ろだけを見る。
"""

import re

BLOCK_HEADING = "【誤答選択肢の解説】"

# 「B: 説明」「B：説明」「B) 説明」のいずれも受ける。
LINE = re.compile(r"^\s*([A-E])\s*[:：)）.]\s*(.+)$")


def split_choice_explanations(explanation: str) -> tuple[str, dict[str, str]]:
    """(見出しブロックを取り除いた本文, {選択肢キー: 解説}) を返す。

    見出しが無ければ本文はそのまま、辞書は空。
    """
    if not explanation or BLOCK_HEADING not in explanation:
        return explanation, {}

    body, _, block = explanation.partition(BLOCK_HEADING)

    per_choice: dict[str, str] = {}
    current = None
    for line in block.split("\n"):
        match = LINE.match(line)
        if match:
            current = match.group(1)
            per_choice[current] = match.group(2).strip()
        elif current and line.strip():
            # 折り返した続きの行は直前の選択肢にくっつける。
            per_choice[current] = f"{per_choice[current]} {line.strip()}"

    return body.strip(), per_choice


def merge_into_text(explanation: str, per_choice: dict[str, str]) -> str:
    """構造化した選択肢ごとの解説を、本文末尾の見出しブロックに畳み直す。

    選択肢ごとの表示に対応していない経路（管理画面の編集など）向けの
    後方互換。
    """
    if not per_choice:
        return explanation
    lines = [f"{key}: {text}" for key, text in sorted(per_choice.items())]
    body = (explanation or "").strip()
    return f"{body}\n\n{BLOCK_HEADING}\n" + "\n".join(lines) if body else (
        f"{BLOCK_HEADING}\n" + "\n".join(lines)
    )
