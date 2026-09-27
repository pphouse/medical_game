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

見出しより後ろには、選択肢の解説だけでなく出典表記も続く。国試の設問文と
選択肢は厚生労働省の Public Data License 1.0 で、出典の表示が条件になって
いる。落とすとライセンス違反になるので、本文側へ戻す。
"""

import re

BLOCK_HEADING = "【誤答選択肢の解説】"

# 受ける書き方は2通り:
#   B: 前壁中隔梗塞は…            （CBT の取り込みバッチ）
#   A「腹部単純CT」: 被曝を伴い…   （国試。どの選択肢かを読んで分かるように
#                                   選択肢の文言を添えてある）
# 後者の「…」は選択肢の横に並べる時点で重複するので、取り込まない。
# 選択肢の文言は横に並べる時点で重複するので取り込まない。会話文の選択肢は
# 「「受動喫煙は…です」」のように入れ子になるため、閉じ括弧は最後のものまで
# 貪欲に読む（区切りをコロンに限ることで行き過ぎを防ぐ）。
LABELLED = re.compile(r"^\s*([A-F])\s*(?:[「『].*[」』]|[(（].*[)）])\s*[:：]\s*(.+)$")
PLAIN = re.compile(r"^\s*([A-F])\s*[:：)）.]\s*(.+)$")


def _match_choice(line):
    return LABELLED.match(line) or PLAIN.match(line)


# 出典表記と注記。ここから先は選択肢の解説ではない。
NOTE_LINE = re.compile(r"^\s*(?:※|\*|出典|https?://)")


def split_choice_explanations(explanation: str) -> tuple[str, dict[str, str]]:
    """(見出しブロックを取り除いた本文, {選択肢キー: 解説}) を返す。

    見出しが無ければ本文はそのまま、辞書は空。
    """
    if not explanation or BLOCK_HEADING not in explanation:
        return explanation, {}

    body, _, block = explanation.partition(BLOCK_HEADING)

    per_choice: dict[str, str] = {}
    trailing: list[str] = []
    current = None
    for line in block.split("\n"):
        if trailing or NOTE_LINE.match(line):
            # 出典・注記に入ったら、以降はすべて本文側に戻す。折り返しの
            # 続き行として選択肢の解説にくっつけてしまわないようにする。
            trailing.append(line)
            continue
        match = _match_choice(line)
        if match:
            current = match.group(1)
            per_choice[current] = match.group(2).strip()
        elif current and line.strip():
            # 折り返した続きの行は直前の選択肢にくっつける。
            per_choice[current] = f"{per_choice[current]} {line.strip()}"

    body = body.strip()
    tail = "\n".join(trailing).strip()
    if tail:
        body = f"{body}\n\n{tail}" if body else tail
    return body, per_choice


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
