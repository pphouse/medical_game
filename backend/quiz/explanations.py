"""解説文の定型文を落とす。

過去問の取り込みバッチには、解説の末尾に決まり文句が付いてくる:

    出典：厚生労働省ホームページ 第118回医師国家試験 A001
    https://www.mhlw.go.jp/.../tp240424-01.html
    （設問文および選択肢は本アプリの表示形式に整形しています）

解説として読む中身が無いうえ、演習画面では毎問これが出て邪魔になるので、
表示に載せない。出典の行（どの回のどの問題か）は残す — 引用元を示す
必要があるのと、学習者にとっても「第118回A001」は手掛かりになる。
"""

import re

# 落とす行。行まるごと一致で消すので、解説本文の途中にたまたま同じ語が
# 出てきても巻き込まない。
DROP_LINE_PATTERNS = (
    # 出典URL（厚労省の過去問ページなど）だけの行
    re.compile(r"^\(?（?\s*https?://\S+\s*\)?）?$"),
    # 表示形式についての注記
    re.compile(r"^[（(].*表示形式.*整形.*[)）]$"),
    # 解説の作成者についての注記
    re.compile(r"^[※*].*(アプリ編集部|過去問には解説は含まれ).*$"),
)


def strip_boilerplate(explanation: str) -> str:
    """解説から定型文の行を落とす。空行の重なりも1つにまとめる。"""
    if not explanation:
        return explanation
    kept = []
    for line in explanation.split("\n"):
        stripped = line.strip()
        if any(p.match(stripped) for p in DROP_LINE_PATTERNS):
            continue
        kept.append(line.rstrip())
    # 行を抜いた跡に空行が続くので詰める。
    out = []
    for line in kept:
        if not line.strip() and (not out or not out[-1].strip()):
            continue
        out.append(line)
    return "\n".join(out).strip()
