"""解説文の定型文を落とす。

過去問の取り込みバッチは、解説の末尾に決まり文句を付けてくる:

    出典：厚生労働省ホームページ 第118回医師国家試験 A001
    https://www.mhlw.go.jp/.../tp240424-01.html
    （設問文および選択肢は本アプリの表示形式に整形しています）

解説として読む中身が無いうえ、演習画面では毎問これが出て邪魔になるので、
表示に載せない。出典の行（どの回のどの問題か）は残す — 引用元を示す必要が
あるのと、学習者にとっても「第118回A001」は手掛かりになる。

行まるごとが定型文のときだけでなく、URLと注記が1行に並んでいる書き方
（``https://... ／設問文および選択肢を本アプリの表示形式に整形``）にも
対応する。取り込み時期によって書式が揺れているため。本文の途中に出てくる
URL（参考文献など）は消さない。
"""

import re

# 行まるごとを落とすパターン。
DROP_LINE_PATTERNS = (
    # 出典URLだけの行（前後に括弧やスラッシュが付くこともある）
    re.compile(r"^[（(\[]?\s*https?://\S+\s*[)）\]]?$"),
    # 表示形式についての注記だけの行
    re.compile(r"^[（(※*]*\s*設問文および選択肢[^\n]*表示形式[^\n]*[)）]?\s*$"),
    # 解説の作成者についての注記だけの行
    re.compile(r"^[※*]*\s*(?=[^\n]*(?:アプリ編集部|過去問には解説は含まれ))[^\n]*$"),
)

# 行の途中に紛れ込んだときに削る断片。行ごと落とす前に先に抜く。
INLINE_PATTERNS = (
    # 「／設問文および選択肢を本アプリの表示形式に整形（しています）」など、
    # 区切り記号つきで URL のうしろに続く形。
    re.compile(r"[／/、,]?\s*[（(]?設問文および選択肢[はをに][^\n）)]*表示形式[^\n）)]*[)）]?"),
    # 「※この解説はアプリ編集部が作成したものです。厚生労働省が公表する
    # 過去問には解説は含まれません。」の類。
    re.compile(r"[※*]?\s*[^\n。]*アプリ編集部[^\n]*?(?:。|$)"),
    re.compile(r"[※*]?\s*[^\n。]*過去問には解説は含まれ[^\n]*?(?:。|$)"),
)


# 出典の行に URL が同居している書き方（`出典：… https://…`）向け。行に
# 「出典」がある場合だけ URL を落とす。本文中の参考リンクは残したいので、
# どこでも消してよいわけではない。
SOURCE_URL = re.compile(r"\s*[（(\[]?https?://\S+[)）\]]?")


def strip_boilerplate(explanation: str) -> str:
    """解説から定型文を落とす。空行の重なりも1つにまとめる。"""
    if not explanation:
        return explanation

    kept = []
    for line in explanation.split("\n"):
        for pattern in INLINE_PATTERNS:
            line = pattern.sub("", line)
        if "出典" in line:
            line = SOURCE_URL.sub("", line)
        stripped = line.strip()
        if any(p.match(stripped) for p in DROP_LINE_PATTERNS):
            continue
        # 断片を抜いた結果、区切り記号や括弧だけが残ることがある。
        if stripped and not re.search(r"[^\s／/、,（()）\[\]．.。-]", stripped):
            continue
        kept.append(line.rstrip())

    out = []
    for line in kept:
        if not line.strip() and (not out or not out[-1].strip()):
            continue
        out.append(line)
    return "\n".join(out).strip()
