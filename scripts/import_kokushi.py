#!/usr/bin/env python3
"""厚生労働省が公表する医師国家試験の過去問を取り込んでバッチJSONを作る。

出典と利用条件
--------------
厚生労働省ホームページは Public Data License 1.0 を採用しており、出典を明示し、
編集した場合はその旨を併記して国の作成物と誤認させない限り、複製・翻案・商用
利用が認められている。本スクリプトが生成する各問には `source_note` として
出典表記を付与し、解説欄にも同じ表記を埋め込む。

第三者の過去問サイト（問題の整形・分類・解説を独自に加えた編集著作物）からは
取得しない。取得元は厚労省の公式PDFのみに限定する。

グリフの解決
------------
国試PDFの本文フォントは ToUnicode CMap を持たない部分集合が混ざっており、
抽出器はそこを埋められない。pdfplumber は "(cid:9479)" を、PyMuPDF は生の
コード（"\\x02"）を返す。後者は一見ふつうの日本語に紛れるため見落としやすく、
実際に第114〜116回の268問が "\\x02か月の乳児"（正しくは "2か月の乳児"）の
形で取り込まれていた。さらに ToUnicode を持っていてもその中身が誤っている
フォントがあり、"RhD(安)"（正しくは "RhD(−)"）、"全身Ø怠感"（倦怠感）、
"末Ü神経"（末梢神経）のように何食わぬ顔で別の字になる。

そこで次の順に解決し、決まらなかった文字を含む設問は取り込まない。

1. 抽出器が解決できたものはそれを使う（記号フォントの既知の誤りだけ補正）。
2. /Encoding /Differences のグリフ名から復元する。ただし信用するのは実際に
   描画して同定した Adobe-Japan1 のCID名（cNNNN）と AGL の標準名だけで、
   uniXXXX を名乗る名前は使わない（ToUnicode が採用しなかった名前は字形と
   食い違う。同じ 〈 が uni002D.c00F4 / uni6B63 / uni81D3 と別名で現れる）。
3. もう一方の抽出器が解決できていれば座標で突き合わせて借りる。
4. それでも決まらなければ設問ごと落とす。

最後に「出てよい文字」の白名簿で本文を通し、外れたら落とす。化け方は回ごと・
フォントごとに変わるため、化けた字を列挙する方式では次の回で漏れる。

取り込まないもの
----------------
- 別冊（画像）を参照する問題: 別冊PDFは患者写真等を含み PDL1.0 の対象外に
  なりうるため除外する。厚労省ページ自身も「実際に出題された画像と異なるものが
  あります」と注記している。
- 連問: 「次の文を読み、47、48の問いに答えよ。」に続く症例文を複数の設問が
  共有する形式。設問文が「診断はどれか。」だけになり単独で成立しない。
- 複数選択（「2つ選べ」等）と計算問題: 現行スキーマが「選択肢ちょうど5個・
  正解1つ」のため入らない。
- 本文の抽出に失敗したもの: グリフを解決できなかった箇所が残るもの、および
  グリフが別の字に化けたもの。誤読の原因になるため落とす。
- 選択肢が ａ〜ｅ の5個そろわないもの: 抽出失敗の可能性があるため落とす。

使い方
------
    for e in 119 118 117 116 115 114; do
        python scripts/import_kokushi.py --exam $e \
            --out backend/quiz/management/commands/data/kokushi_$e.json
    done
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover - 実行環境の案内
    sys.exit(
        "pdfplumber が必要です: pip install -r requirements-scripts.txt\n"
        "（pypdf は本PDFのフォント埋め込みを解決できず文字化けするため使わないこと）"
    )

# 回ごとの公開ページとPDFの命名規則。厚労省は回ごとにURLが変わるため表で持つ。
# 注意: PDF の接頭辞はページ名と一致しないことがある。第117回はページが
# tp230502-01.html なのに PDF は tp220502-01*.pdf である。回を追加するときは
# 必ず公開ページの href を確認すること（推測すると404になる）。
_BASE = "https://www.mhlw.go.jp/seisakunitsuite/bunya/kenkou_iryou/iryou/topics"
EXAMS = {
    119: {"page": f"{_BASE}/tp250428-01.html", "pdf_base": f"{_BASE}/dl", "prefix": "tp250428-01"},
    118: {"page": f"{_BASE}/tp240424-01.html", "pdf_base": f"{_BASE}/dl", "prefix": "tp240424-01"},
    117: {"page": f"{_BASE}/tp230502-01.html", "pdf_base": f"{_BASE}/dl", "prefix": "tp220502-01"},
    116: {"page": f"{_BASE}/tp220421-01.html", "pdf_base": f"{_BASE}/dl", "prefix": "tp220421-01"},
    115: {"page": f"{_BASE}/tp210416-01.html", "pdf_base": f"{_BASE}/dl", "prefix": "tp210416-01"},
    114: {"page": f"{_BASE}/tp200421-01.html", "pdf_base": f"{_BASE}/dl", "prefix": "tp200421-01"},
}

BLOCKS = "abcdef"  # 甲乙丙丁戊己 → 正答表の A〜F に対応

CHOICE_MARKS = "ａｂｃｄｅ"
CHOICE_KEYS = ["A", "B", "C", "D", "E"]

# ページ下部のノンブル。抽出テキストでは "DKIX-0１-AH-2" や、字が二重に
# なった "DDKKIIXX0011AAHH..iinndddd" の形で紛れ込むので、DKIX を含む行を落とす。
NOISE_LINE = re.compile(r"DKIX|DDKKIIXX|^\s*$")

# 別冊（画像）を参照している設問。これらは取り込まない。
IMAGE_REF = re.compile(r"別冊|を別に示す|別に示す")

# 図表を参照する設問。「家系図を示す」「以下に示す」と書いてあるのに参照先が
# 本文に入っていないものは、図が無いと解けない。会話文や表を本文に取り込めて
# いる設問は必ず長くなるので、本文の長さで見分ける。実際に「家系図を示す。
# この疾患の遺伝形式はどれか。」(41字) のような解きようのない設問が公開まで
# 通り抜けていた。
FIGURE_REF = re.compile(
    r"(家系図|図|表|写真|画像|グラフ|シェーマ|電気泳動|カレンダー|推移)を(以下に|別に)?示す"
    # 「模式図に示す」のように助詞が「に」の形。表は本文に取り込めるので
    # 「表に示す」は含めない（実際に取り込めている設問がある）。
    r"|(模式図|図|写真|画像|グラフ|シェーマ)に示す"
)
FIGURE_REF_MIN_BODY = 120

# 複数選択・計算問題。現行スキーマに入らない。
MULTI_SELECT = re.compile(r"[２2３3４4]\s*つ選べ")

# 連問の導入。「次の文を読み、47、48の問いに答えよ。」に続く症例文を複数の設問が
# 共有する形式。個々の設問文は「診断はどれか。」のように単独では成立しないため、
# 現状は取り込まない（将来 question_set として扱う余地はある）。
SERIES_HEAD = re.compile(r"次の文を読み[、,]\s*([0-9０-９、,〜～\-]+?)\s*の問いに答えよ")

# pdfplumber がグリフを解決できなかった箇所。本文に "(cid:7674)" の形で残る。
CID_ARTIFACT = re.compile(r"\(cid:\d+\)")

# 解決できなかった1文字を表す番人。ここに残ったまま出力されることは無く、
# UNRESOLVED を含む設問は取り込み時に必ず落とす（後述の is_unusable）。
UNRESOLVED = "�"

# 抽出に失敗した痕跡。PDFのフォントが ToUnicode を持たないとき、pdfplumber は
# "(cid:N)" を、PyMuPDF は生のコード（制御文字）をそのまま出す。制御文字は
# 一見ふつうの日本語に紛れるため見落としやすく、実際に第114〜116回で268問が
# "\x02か月の乳児"（正しくは "2か月の乳児"）のような形で取り込まれていた。
# 解決の網から漏れた文字は必ずここで捕まえて設問ごと落とす。
#
# 範囲を \x00-\x1f で書くと C1（\x80-\x9f）が漏れる。実際に "全身\x8b怠感" が
# それで素通りしたので、Unicode の分類で判定する（Cc 制御・Cf 書式・Cn 未割当・
# Co 私用領域・Cs サロゲート）。タブと改行は行の組み立てに使うので除く。
_UNUSABLE_CATEGORIES = frozenset({"Cc", "Cf", "Cn", "Co", "Cs"})
_CID_LEFTOVER = re.compile(r"\(cid:\d+\)")


def is_unusable(text: str) -> bool:
    """抽出に失敗した文字を含むか。

    UNRESOLVED（U+FFFD）は分類が So で _UNUSABLE_CATEGORIES に入らないため
    明示的に見る。ここを category 判定だけにしていて35問取りこぼした。
    """
    if UNRESOLVED in text or _CID_LEFTOVER.search(text):
        return True
    return any(
        ch not in "\t\n" and unicodedata.category(ch) in _UNUSABLE_CATEGORIES
        for ch in text
    )

# 解決はされたが別の字に化けた箇所。フォントの ToUnicode が誤っている場合、
# 抽出器は何食わぬ顔で別の字を返すので (cid:) や制御文字の網に掛からない。
# 実際に "筋萎縮性側索硬化症ÕALS×"（正しくは 〈ALS〉）、"全身Ø怠感"（倦怠感）、
# "末Ü神経"（末梢神経）のような形で紛れ込んでいた。
#
# 化け方は回ごと・フォントごとにばらばらで、出てくる字を列挙しても次の回で
# 別の字になる。そこで「出てよい文字」を決めて、外れたら設問ごと落とす。
# 取りこぼしは stats に出るので、増えたときに気づける。
_ACCENTED_OK = "öéç"
"""医学の人名で実際に使う文字だけを許す。

第114〜119回の全用例を確認した結果、正当なのは Schönlein / Sjögren（ö）、
Barré / café au lait（é）、Behçet（ç）の3字だけだった。同じラテン文字でも
Õ Ø ä ì Ü ò Ù は例外なく 〈 倦 梢 の化けで、許すと本文が壊れる。新しい回で
Müller の ü のような正当な字が出たら、実際の用例を確かめてから足すこと。
"""

_SYMBOLS_OK = "−±×÷≦≧≒≠≪≫→←↑↓℃°‰′″・※…—–‐µʼ"


def _is_expected_char(ch: str) -> bool:
    o = ord(ch)
    if ch in "\n\t" or 0x20 <= o <= 0x7E:          # ASCII
        return True
    if 0x3000 <= o <= 0x30FF or 0xFF00 <= o <= 0xFFEF:  # 和文の記号・かな・全角
        return True
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF:
        return True                                 # 漢字（拡張・互換を含む）
    if 0x0370 <= o <= 0x03FF:                       # ギリシャ文字（α波、β遮断薬）
        return True
    # ローマ数字（JCS Ⅱ-10、第Ⅷ因子、WAIS-Ⅲ、Ⅱ/Ⅵの拡張期雑音）、
    # 丸数字（診療録問題の①②③）、幾何記号（図中の●）。国試では常用される。
    if 0x2150 <= o <= 0x218F or 0x2460 <= o <= 0x24FF or 0x25A0 <= o <= 0x25FF:
        return True
    return ch in _ACCENTED_OK or ch in _SYMBOLS_OK


def has_broken_glyph(text: str) -> bool:
    """字化けの疑いがある文字を含むか。"""
    return not all(_is_expected_char(ch) for ch in text)

# 設問の通し番号で始まる行（例: "13 Brugada症候群における…"）
Q_START = re.compile(r"^(\d{1,3})[ 　]+(\S.*)$", re.MULTILINE)

# 設問文は必ず問いかけで終わる。終わっていないものは切り出しに失敗している
# （表の断片や、受験上の注意ページの文面を拾ってしまったもの）。
TRUSTWORTHY_STEM = re.compile(
    r"(どれか|選べ|答えよ|求めよ|示せ|述べよ|答えは|正しいか|何か|"
    r"[Ww]hich|[Ww]hat|[Hh]ow)\s*[。．\?？]?\s*$"
)

# 文の途中から始まっている設問文。前の設問の折り返しを起点にしてしまった
# ときに出る（"分間様子をみたが、止血しないため…"）。ひらがな・句読点・
# 閉じ括弧・単位記号で始まる設問文は日本語として成立しない。
BAD_STEM_START = re.compile(r"^[ぁ-ん、。，．％%）\)\]〕」』,;:／/–—-]")

# category は出題基準の区分が過去問には付かないため、設問文からキーワードで
# 暫定的に割り当てる。取り込みは status=pending なので、レビュー時に人の目で
# 確定させる前提の「たたき台」である。既存カテゴリ名に揃えて分裂を防ぐ。
#
# 注意: 「血圧」「発熱」「神経」のような語は臨床問題のバイタル記載や一般的な
# 記述に必ず現れるため、キーワードに入れると全問がその分野に吸い寄せられる。
# 実際に入れて試したところ循環器系が199問中50問になり使い物にならなかった。
# 分野を一意に特定できる語だけを並べ、判定できないものは既定値に落とす。
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("集団に対する医療", ("疫学", "公衆衛生", "介護保険", "医療保険", "健康保険", "感染症法",
                          "母子保健", "学校保健", "産業保健", "医療計画", "特定健診", "国民皆保険")),
    ("医の倫理と患者の権利、医師としての責務", ("インフォームド・コンセント", "医の倫理", "守秘義務",
                                                "医師法", "臨床研究", "利益相反", "アドバンス・ケア・プランニング")),
    ("精神系", ("統合失調", "うつ病", "双極性障害", "せん妄", "パニック症", "強迫症",
                "摂食障害", "神経性やせ症", "アルコール依存", "思路障害", "妄想", "幻聴", "認知行動療法")),
    ("産婦人科系", ("妊娠", "分娩", "産褥", "子宮", "卵巣", "月経", "胎児", "乳腺", "更年期", "胎盤")),
    ("小児系", ("新生児", "乳児健診", "予防接種", "川崎病", "熱性けいれん", "先天性心疾患", "低出生体重")),
    ("循環器系", ("心筋梗塞", "狭心症", "心不全", "不整脈", "心房細動", "心電図", "弁膜症",
                  "大動脈解離", "心筋症", "心膜炎", "冠動脈", "房室ブロック")),
    ("呼吸器系", ("肺炎", "気管支喘息", "COPD", "慢性閉塞性肺疾患", "肺癌", "気胸", "結核",
                  "呼吸不全", "胸水", "間質性肺", "睡眠時無呼吸")),
    ("消化器系", ("胃癌", "大腸癌", "潰瘍性大腸炎", "Crohn", "肝硬変", "肝炎", "胆石", "胆嚢炎",
                  "膵炎", "食道", "虫垂炎", "腸閉塞", "消化性潰瘍", "黄疸")),
    ("腎・尿路系", ("腎不全", "糸球体腎炎", "ネフローゼ", "透析", "尿路結石", "腎盂腎炎",
                    "慢性腎臓病", "尿細管", "血液浄化")),
    ("神経系", ("脳梗塞", "脳出血", "くも膜下出血", "てんかん", "認知症", "Parkinson",
                "髄膜炎", "重症筋無力症", "多発性硬化症", "Guillain", "筋萎縮性側索硬化症")),
    ("内分泌・代謝系", ("糖尿病", "甲状腺", "副腎", "下垂体", "脂質異常症", "痛風",
                        "副甲状腺", "Cushing", "Basedow", "尿崩症")),
    ("血液・造血器・リンパ系", ("貧血", "白血病", "リンパ腫", "血小板減少", "血友病",
                                "骨髄", "多発性骨髄腫", "播種性血管内凝固", "輸血")),
    ("皮膚系", ("皮疹", "紅斑", "水疱", "アトピー性皮膚炎", "白癬", "蕁麻疹", "悪性黒色腫", "乾癬")),
    ("運動器系", ("骨折", "変形性", "骨粗鬆症", "椎間板ヘルニア", "脊柱管狭窄", "関節リウマチ", "腱板")),
    ("眼系", ("視力低下", "網膜", "緑内障", "白内障", "角膜", "結膜炎", "眼底")),
    ("耳鼻咽喉系", ("難聴", "中耳炎", "副鼻腔炎", "喉頭", "扁桃", "Ménière", "めまい", "耳鳴")),
    ("感染症", ("抗菌薬", "敗血症", "インフルエンザ", "HIV", "耐性菌", "院内感染", "ワクチン")),
    ("腫瘍", ("化学療法", "放射線治療", "緩和ケア", "がん検診", "腫瘍マーカー", "転移")),
    ("救急系", ("心肺蘇生", "外傷", "ショック", "熱傷", "中毒", "熱中症", "トリアージ")),
]
# キーワードで分野を特定できなかったものの受け皿。CBT側の実カテゴリに混ぜると
# 統計が汚れるため、レビューで再分類すべきものだと分かる名前にしておく。
DEFAULT_CATEGORY = "医師国家試験（分類未確定）"


def classify(text: str) -> str:
    for cat, keys in CATEGORY_RULES:
        if any(k in text for k in keys):
            return cat
    return DEFAULT_CATEGORY


def fetch(url: str, dest: Path) -> Path:
    """未取得なら落とす。取得済みなら再利用（厚労省への不要なアクセスを避ける）。"""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "medical-game-importer"})
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as fh:
        fh.write(resp.read())
    return dest


def _clean(lines: list[str]) -> list[str]:
    return [ln.rstrip() for ln in lines if not NOISE_LINE.search(ln)]


# --- グリフの解決 --------------------------------------------------------
#
# 国試PDFの本文フォントは ToUnicode を持たない部分集合が混ざっており、
# そのままでは文字が落ちる。3段構えで解決し、どれでも決まらなかった文字だけを
# UNRESOLVED にする。
#
#   1. 抽出器が解決できたものはそれを使う。
#   2. /Encoding /Differences のグリフ名から復元する（第114〜116回）。
#   3. もう一方の抽出器が解決できていれば座標で突き合わせて借りる（第117〜119回）。

# Adobe-Japan1 のCID番号がそのままグリフ名になっていて Unicode に対応表を
# 持たないもの。PDFから該当グリフを実際に描画して目視で同定した。
# 数字は c2690〜c2699 の10連番で 0〜9 に対応する。
CID_GLYPHS: dict[str, str] = {
    **{f"c{0x2690 + i:04X}": str(i) for i in range(10)},
    "c00EF": "(", "c00F0": ")", "c01FA": "〈", "c01FB": "〉",
    "c4ECF": "疼", "c1F25": "穿", "c1F37": "扁", "c1E5C": "這",
    "c1F1D": "牙", "c2067": "XIII",
}

_CID_CHAR = re.compile(r"^\(cid:(\d+)\)$")

# 記号フォント ZZ-PIStd-819 は ToUnicode を持っているが、その中身が誤っている。
# 抽出器は素通しするので "RhD(安)" のような一見もっともらしい本文になり、
# (cid:) や制御文字の網にも掛からない。実際に該当グリフを描画して確かめた
# 対応が下表で、いずれも検査所見でよく使う記号だった（"RhD(−)" が正しい）。
PI_STD_FONT = "ZZ-PIStd"
PI_STD_GLYPHS = {
    "粟": "↓", "或": "→", "袷": "+", "安": "−", "庵": "×", "案": "±",
}


def _fix_symbol_font(fontname: str, text: str) -> str:
    """記号フォントの誤った ToUnicode を補正する。"""
    if PI_STD_FONT not in fontname:
        return text
    return "".join(PI_STD_GLYPHS.get(ch, ch) for ch in text)

# Adobe-Japan1 のプロポーショナル欧文の並び。Identity-H で ToUnicode を持たない
# フォント（第117〜119回の学名表記など）はCIDがそのまま出るので、この並びで戻す。
# PyMuPDF の解決結果と座標で突き合わせて確認した（CID 9479→'C' から始まる
# "Chlamydia pneumoniae" がそのまま復元できる）。
# 1つのグリフが複数文字に対応するもの。座標で PyMuPDF の結果を借りる経路は
# 1文字しか受け取れず、「第XIII因子」が「第X因子」になってしまう（第117回
# D41・F21 で実際に起きた。第X因子はビタミンK依存性なので、設問の正答が
# 成立しなくなる）。CIDから直に引いて xref より優先する。
_AJ1_MULTI: dict[int, str] = {
    0x2067: "XIII",
}

_AJ1_LATIN: dict[int, str] = {
    9444: " ",
    **{9477 + i: chr(ord("A") + i) for i in range(26)},
    **{9509 + i: chr(ord("a") + i) for i in range(26)},
}


def _glyph_char(name: str) -> str | None:
    """グリフ名から文字を復元する。決められなければ None。

    "uni4EE4" のような Unicode を名乗る名前は信用しない。この関数を通るのは
    フォントの ToUnicode CMap が対応を持たなかった符号だけであり、CMap が
    採用しなかった名前は実際の字形と食い違う。実際に描画して確かめたところ、
    第116回の "全身倦怠感" の 倦 はグリフ名が uni4EE4（令）、第114回の
    "〈ABR〉" は uni002D と uni0041（-とA）だった。さらに同じ 〈 が
    uni002D.c00F4 / uni6B63 / uni81D3 / uni6CD5 と別々の名前で現れており、
    名前と字形に対応関係が無い。名前どおりに置くと本文が壊れる。

    信用するのは
      - CID_GLYPHS: 実際にPDFから描画して目視で同定した Adobe-Japan1 のCID
      - Adobe Glyph List の標準名（gamma, arrowright など）
    の2つだけにする。
    """
    if name in CID_GLYPHS:
        return CID_GLYPHS[name]
    if name.startswith("uni"):
        return None
    try:
        from fontTools.agl import toUnicode

        return toUnicode(name.split(".")[0]) or None
    except Exception:  # pragma: no cover - fontTools 未導入時
        return None


_ENC_REF = re.compile(r"/Encoding\s+(\d+) 0 R")
_DIFFERENCES = re.compile(r"/Differences\s*\[(.*?)\]", re.S)


def _encoding_tables(path: Path) -> dict[str, dict[int, str]]:
    """フォント名 -> {コード: 文字} を /Differences から作る。

    PyMuPDF 側のフォント名には部分集合の接頭辞（"EMJJID+"）が付かないことが
    あるので、接頭辞なしの別名も張る。ただし同じ書体の別々の部分集合が食い違う
    対応を持つことがあり（同じコードが片方では "2"、もう片方では "疼"）、
    その場合は誤読を招くので別名を消す。
    """
    import pymupdf

    doc = pymupdf.open(path)
    tables: dict[str, dict[int, str]] = {}
    for pno in range(doc.page_count):
        for xref, _ext, _typ, basefont, _name, _enc in doc[pno].get_fonts(full=False):
            if basefont in tables:
                continue
            obj = doc.xref_object(xref)
            ref = _ENC_REF.search(obj)
            diff = _DIFFERENCES.search(doc.xref_object(int(ref.group(1)))) if ref else None
            table: dict[int, str] = {}
            if diff:
                code: int | None = None
                for token in diff.group(1).split():
                    if token.startswith("/"):
                        if code is not None:
                            ch = _glyph_char(token[1:])
                            if ch:
                                table[code] = ch
                            code += 1
                    else:
                        try:
                            code = int(token)
                        except ValueError:
                            pass
            tables[basefont] = table
    doc.close()

    aliases: dict[str, dict[int, str] | None] = {}
    for basefont, table in tables.items():
        short = basefont.split("+")[-1]
        if short == basefont:
            continue
        if short in aliases:
            known = aliases[short]
            if known is not None and any(known.get(k, v) != v for k, v in table.items()):
                aliases[short] = None  # 食い違うので使わない
        else:
            aliases[short] = table
    for short, table in aliases.items():
        if table is not None and short not in tables:
            tables[short] = table
    return tables


def _crossref_table(path: Path) -> dict[tuple[str, int], str]:
    """(フォント名, CID) -> 文字 を PyMuPDF の解決結果から学習する。

    第117〜119回の欧文フォントは Identity-H かつ ToUnicode 無しで、pdfplumber は
    "(cid:9479)" しか返せない。一方 PyMuPDF は同じ文字を 'C' と読めている。
    そこで両者の文字を座標で突き合わせ、CIDと文字の対応を1冊ぶん学習してから
    全体に適用する。

    PyMuPDF は既定で CropBox を原点に取るため MediaBox に揃える。それでも
    ベースラインの取り方の差でy座標に一定のずれが残るので、両者が一致した文字
    からずれ幅を推定してから対応付ける。矛盾する対応が観測されたCIDは信用せず
    捨てる（誤読を作るくらいなら設問ごと落とすほうがよい）。
    """
    import pymupdf

    doc = pymupdf.open(path)
    for page in doc:
        page.set_cropbox(page.mediabox)

    learned: dict[tuple[str, int], str] = {}
    conflicts: set[tuple[str, int]] = set()
    with pdfplumber.open(path) as pdf:
        for pno, plumber_page in enumerate(pdf.pages):
            if pno >= doc.page_count:
                break
            mu: list[tuple[float, float, str]] = []
            for blk in doc[pno].get_text("rawdict")["blocks"]:
                for ln in blk.get("lines", []):
                    for sp in ln["spans"]:
                        for ch in sp["chars"]:
                            mu.append((ch["bbox"][0], ch["bbox"][1], ch["c"]))
            if not mu:
                continue

            # 両者が同じ文字を出している箇所からy方向のずれを求める。
            by_x: dict[float, list[tuple[float, str]]] = {}
            for x0, y0, ch in mu:
                by_x.setdefault(round(x0, 1), []).append((y0, ch))
            deltas = []
            for ch in plumber_page.chars:
                for y0, mc in by_x.get(round(ch["x0"], 1), ()):
                    if mc == ch["text"]:
                        deltas.append(y0 - ch["top"])
            if not deltas:
                continue
            deltas.sort()
            dy = deltas[len(deltas) // 2]

            index = {(round(x0, 1), round(y0 - dy, 1)): ch for x0, y0, ch in mu}
            for ch in plumber_page.chars:
                m = _CID_CHAR.match(ch["text"])
                if not m:
                    continue
                got = index.get((round(ch["x0"], 1), round(ch["top"], 1)))
                if not got or is_unusable(got):
                    continue
                key = (ch["fontname"], int(m.group(1)))
                if key in conflicts:
                    continue
                if learned.setdefault(key, got) != got:
                    conflicts.add(key)
                    del learned[key]
    doc.close()
    return learned


# 組合せ問題（"蕁麻疹 —— H1受容体拮抗薬内服"）の左右2列の間隔。実測では
# 列の境目が 73〜109pt あるのに対し、行内のふつうの字間は 2.5pt しかない。
# 20pt に置けばどちらとも十分に離れている。
COLUMN_GAP = 20.0
COLUMN_SEPARATOR = "—"

# 添字・上付きを本文と同じ行として扱うための許容量。既定の 3pt では
# "H1受容体拮抗薬" の 1 が行から外れて "H 受容体拮抗薬内服" + "1" になる。
# 行送りは約20ptあるので、6pt では隣の行と混ざらない。
LINE_Y_TOLERANCE = 6.0

# 均等割りで開いた字間（"疥 癬"）。列の区切りは上で COLUMN_SEPARATOR に
# 置き換えたあとなので、ここに残る和文どうしの1個の空白は字間調整でしかない。
KINSOKU_SPACE = re.compile(r"(?<=[ぁ-んァ-ヶ一-龥々]) (?=[ぁ-んァ-ヶ一-龥々])")


def _with_column_separators(chars: list[dict]) -> list[dict]:
    """左右2列に組まれた箇所へ区切りを差し込む。

    extract_text() は語を1個の空白でつなぐため、そのままでは列の境目が
    字間と区別できなくなる（"疥 癬 外陰部" が「疥/癬/外陰部」に見える）。
    間隔が空いている箇所に印を入れてから渡す。
    """
    out: list[dict] = []
    for ch in sorted(chars, key=lambda c: (round(c["top"] / LINE_Y_TOLERANCE), c["x0"])):
        if out:
            prev = out[-1]
            same_line = abs(prev["top"] - ch["top"]) < LINE_Y_TOLERANCE
            if same_line and ch["x0"] - prev["x1"] > COLUMN_GAP:
                mid = (prev["x1"] + ch["x0"]) / 2
                out.append({**prev, "text": COLUMN_SEPARATOR,
                            "x0": mid - 1, "x1": mid + 1})
        out.append(ch)
    return out


def _pdfplumber_lines(path: Path) -> list[str]:
    """pdfplumber の行構造のまま、解決できなかったグリフを埋めて返す。

    page.extract_text() は文字単位のフォント情報を捨ててしまうので、
    page.chars を直接直してから同じ抽出関数に渡す。行の切り方は変わらない。
    """
    from pdfplumber.utils import extract_text

    enc = _encoding_tables(path)
    xref = _crossref_table(path)
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chars = []
            for ch in page.chars:
                m = _CID_CHAR.match(ch["text"])
                if m:
                    code = int(m.group(1))
                    table = enc.get(ch["fontname"], {})
                    # /Differences を持たないフォント（Identity-H）では、
                    # ここに出る番号は符号ではなく Adobe-Japan1 のCIDそのもの。
                    latin = _AJ1_LATIN.get(code) if not table else None
                    multi = _AJ1_MULTI.get(code) if not table else None
                    fixed = (table.get(code)
                             or multi
                             or xref.get((ch["fontname"], code))
                             or latin
                             or UNRESOLVED)
                    ch = {**ch, "text": fixed}
                else:
                    fixed = _fix_symbol_font(ch["fontname"], ch["text"])
                    if fixed != ch["text"]:
                        ch = {**ch, "text": fixed}
                chars.append(ch)
            if not chars:
                pages.append("")
                continue
            text = extract_text(_with_column_separators(chars),
                                y_tolerance=LINE_Y_TOLERANCE)
            pages.append(KINSOKU_SPACE.sub("", text))
    return _clean([ln for page in pages for ln in page.split("\n")])


def _pymupdf_lines(path: Path) -> list[str]:
    """PyMuPDF で1行ずつ復元する。

    古い回（第114〜116回）の PDF は pdfplumber がグリフを解決できず
    "(cid:NNNN)" を大量に残す。PyMuPDF は同じPDFを正しく読めるが、
    行オブジェクトが文字単位に割れている（"ａ" "肥" "満" が別の行になる）ため、
    y座標でまとめ直してから x 順に連結する。
    """
    import pymupdf  # 遅延 import。cid が出た回でしか使わない。

    enc = _encoding_tables(path)
    doc = pymupdf.open(path)
    out: list[str] = []
    for page in doc:
        rows: dict[int, list[tuple[float, str]]] = {}
        for blk in page.get_text("rawdict")["blocks"]:
            for ln in blk.get("lines", []):
                # PyMuPDF は ToUnicode の無いグリフを生のコード（制御文字）で
                # 返す。span のフォント名から /Differences を引いて直す。
                text = "".join(
                    _fix_symbol_font(sp["font"], "".join(
                        ch["c"] if not is_unusable(ch["c"])
                        else enc.get(sp["font"], {}).get(ord(ch["c"]), UNRESOLVED)
                        for ch in sp["chars"]
                    ))
                    for sp in ln["spans"]
                )
                if not text.strip():
                    continue
                x0, _y0, x1, y1 = ln["bbox"]
                rows.setdefault(round(y1 / 2.0), []).append((x0, x1, text))
        for key in sorted(rows):
            parts = sorted(rows[key])
            # 組合せ問題（"蕁麻疹 —— H1受容体拮抗薬内服"）は左右2列で組まれる。
            # 単純に連結すると列の境目が消えて "蕁麻疹H1受容体拮抗薬内服" になって
            # しまうため、横方向に大きく空いている箇所には区切りを入れ直す。
            buf = [parts[0][2]]
            for i in range(1, len(parts)):
                gap = parts[i][0] - parts[i - 1][1]
                buf.append("　—　" if gap > 12.0 else " ")
                buf.append(parts[i][2])
            joined = "".join(buf)
            # 均等割りで開いた字間（"肥 満"）を詰める。和文どうしの間の空白だけを
            # 落とすので、"FDG-PET での…" のような欧文と和文の間は保つ。
            joined = re.sub(r"(?<=[ぁ-んァ-ヶ一-龥])\s+(?=[ぁ-んァ-ヶ一-龥])", "", joined)
            out.append(joined)
    doc.close()
    return _clean(out)


def _usable_count(lines: list[str]) -> int:
    """その抽出結果から何問取り出せるかを数える（採用判定用）。"""
    n = 0
    for _num, stem, texts in parse_block(lines):
        body = stem + "".join(texts)
        if stem and not is_unusable(body) and not has_broken_glyph(body):
            n += 1
    return n


def pdf_lines(path: Path) -> list[str]:
    """本文を行のリストで返す。抽出器は回ごとに向き不向きがあるため実測で選ぶ。

    - pdfplumber は行の切り方が原文に忠実だが、古い回（第114〜116回）では
      グリフを解決できず "(cid:NNNN)" を大量に残す。
    - PyMuPDF はそれらのグリフを正しく読めるが、行オブジェクトが文字単位に
      割れており、y座標での復元が必要なぶん行構造が崩れる回がある。

    どちらが良いかは回によって逆転しうるので、閾値で決め打ちせず、両方で解析して
    取り出せた問数が多いほうを採用する。グリフ解決を入れた後は全回で pdfplumber が
    上回る（第114回 141→402問など）が、判定は残しておく。
    """
    plumber = _pdfplumber_lines(path)
    if not any(UNRESOLVED in ln for ln in plumber):
        return plumber
    mupdf = _pymupdf_lines(path)
    return mupdf if _usable_count(mupdf) > _usable_count(plumber) else plumber


def pdf_text(path: Path) -> str:
    return "\n".join(pdf_lines(path))


def parse_answers(text: str) -> dict[str, list[str]]:
    """正答値表をパースして {"A001": ["A"], "E028": ["A","C"], "F075": ["40"]} を返す。

    1行に4問ぶんが横並びで入る。列境界が曖昧（複数正答は "A C" や "BD" の形を
    とる）ため、トークンを左から走査し「問番号らしいトークン」で区切る。
    """
    answers: dict[str, list[str]] = {}
    current: str | None = None
    for token in text.split():
        if re.fullmatch(r"[A-F]\d{3}", token):
            current = token
            answers[current] = []
        elif current is not None and re.fullmatch(r"[A-E]+|\d+", token):
            answers[current].append(token)
    return answers


CHOICE_LINE = re.compile(rf"^([{CHOICE_MARKS}])[ 　]+(\S.*)$")


def series_numbers(lines: list[str]) -> set[int]:
    """連問に属する設問番号を集める。

    「次の文を読み、47、48の問いに答えよ。」→ {47, 48}
    「次の文を読み、71〜73の問いに答えよ。」→ {71, 72, 73}
    """
    nums: set[int] = set()
    for line in lines:
        m = SERIES_HEAD.search(line)
        if not m:
            continue
        spec = unicodedata.normalize("NFKC", m.group(1))
        for part in re.split(r"[、,]", spec):
            part = part.strip()
            rng = re.fullmatch(r"(\d+)\s*[〜～\-]\s*(\d+)", part)
            if rng:
                nums.update(range(int(rng.group(1)), int(rng.group(2)) + 1))
            elif part.isdigit():
                nums.add(int(part))
    return nums


def _join_wrapped(parts: list[str]) -> str:
    """折り返された行を1つの文にまとめる。

    和文は行末で切れても空白を入れずに詰めるのが正しいが、そのまま全部を詰めると
    英語の設問（国試には毎回数問ある）が "intracerebralhemorrhage" のように
    単語同士でくっついてしまう。欧文どうしの境目にだけ空白を補う。
    """
    out = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if out and re.search(r"[0-9A-Za-z,.;:)]$", out) and re.match(r"[0-9A-Za-z(]", part):
            out += " "
        out += part
    return out


def _is_choice_line(line: str) -> tuple[str, str] | None:
    """選択肢行なら (記号, 本文) を返す。

    受験上の注意ページには "ａ 保健所長 ａ 氏名変更時" のような2段組の表が
    あり、1行に記号が2つ現れる。これは選択肢ではないので弾く。
    """
    m = CHOICE_LINE.match(line)
    if not m:
        return None
    if re.search(rf"[{CHOICE_MARKS}][ 　]", m.group(2)):
        return None
    return m.group(1), m.group(2)


def parse_block(lines: list[str]) -> list[tuple[int, str, list[str]]]:
    """1ブロックの行列から (設問番号, 設問文, 選択肢5個) を切り出す。

    設問番号の行を起点にすると、受験上の注意ページのマークシート見本
    （"0 1 2 3 4 5 …" が延々と並ぶ）を設問と誤認する。そこで
    「ａ〜ｅ が順に並ぶ5行」を骨格として検出し、その直前を設問文とみなす。
    """
    marks: dict[int, tuple[str, str]] = {}
    for i, line in enumerate(lines):
        got = _is_choice_line(line)
        if got:
            marks[i] = got

    idxs = sorted(marks)
    runs: list[list[int]] = []
    n = 0
    while n < len(idxs):
        if marks[idxs[n]][0] == CHOICE_MARKS[0]:
            seq = [idxs[n]]
            k = n + 1
            for want in CHOICE_MARKS[1:]:
                if k < len(idxs) and marks[idxs[k]][0] == want:
                    seq.append(idxs[k])
                    k += 1
                else:
                    break
            if len(seq) == len(CHOICE_MARKS):
                runs.append(seq)
                n = k
                continue
        n += 1

    out = []
    prev_end = 0
    for r_i, run in enumerate(runs):
        next_start = runs[r_i + 1][0] if r_i + 1 < len(runs) else len(lines)

        # 各選択肢の本文＝記号行 + 折り返し行（次の記号行の手前まで）
        texts = []
        for j, li in enumerate(run):
            stop = run[j + 1] if j + 1 < len(run) else next_start
            parts = [marks[li][1]]
            for cont in lines[li + 1 : stop]:
                # 次の設問の番号行、または連問の導入文に達したら打ち切る。
                # これを見ないと最後の選択肢が次の症例文を丸ごと飲み込む。
                if Q_START.match(cont) or SERIES_HEAD.search(cont):
                    break
                if _is_choice_line(cont):
                    break
                parts.append(cont)
            texts.append(_join_wrapped(parts))

        # 設問文＝直前の設問の選択肢が終わってから ａ 行の手前まで
        stem_lines = lines[prev_end : run[0]]
        # 最後の番号行から始める（前問の選択肢の折り返しを巻き込まないため）
        start = 0
        for k, line in enumerate(stem_lines):
            if Q_START.match(line):
                start = k
        stem_lines = stem_lines[start:]
        prev_end = run[-1] + 1

        if not stem_lines:
            continue
        m = Q_START.match(stem_lines[0])
        if not m:
            continue
        num = int(m.group(1))
        stem = _join_wrapped([m.group(2)] + stem_lines[1:])
        out.append((num, stem, texts))
    return out


def build_explanation(exam: int, block: str, num: int, answer_key: str,
                      choice_text: str, page_url: str) -> str:
    """解説欄。正答と出典表記を必ず含める（PDL1.0 の出典明示要件）。

    医学的な解説は本スクリプトでは生成しない。厚労省は正答のみを公表しており、
    解説は別途執筆して差し替える前提のプレースホルダである。
    """
    quoted = choice_text if len(choice_text) <= 120 else choice_text[:117] + "…"
    return (
        f"正答は {answer_key}「{quoted}」。\n\n"
        "この設問は医師国家試験の過去問です。詳しい解説は準備中で、"
        "内容の確認後に順次追加されます。\n\n"
        f"出典：厚生労働省ホームページ 第{exam}回医師国家試験 {block}{num:03d}\n"
        f"{page_url}\n"
        "（設問文および選択肢は本アプリの表示形式に整形しています）"
    )


def normalize(text: str) -> str:
    """全角英数字を半角に寄せる。医学用語の全角カナはそのまま残す。"""
    return unicodedata.normalize("NFKC", text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exam", type=int, required=True, choices=sorted(EXAMS),
                    help="回数（例: 119）")
    ap.add_argument("--out", required=True, help="出力するバッチJSONのパス")
    ap.add_argument("--cache", default=".cache/kokushi", help="PDFの保存先")
    args = ap.parse_args()

    cfg = EXAMS[args.exam]
    cache = Path(args.cache) / str(args.exam)

    seitou = fetch(f"{cfg['pdf_base']}/{cfg['prefix']}seitou.pdf", cache / "seitou.pdf")
    answers = parse_answers(pdf_text(seitou))
    print(f"正答値表: {len(answers)} 問")

    questions: list[dict] = []
    seen: dict[str, int] = {}
    stats = {"total": 0, "series": 0, "image": 0, "multi": 0, "cid": 0,
             "bad_stem": 0, "duplicate": 0, "bad_choices": 0, "no_answer": 0, "ok": 0}

    for i, block in enumerate(BLOCKS):
        letter = chr(ord("A") + i)
        pdf = fetch(f"{cfg['pdf_base']}/{cfg['prefix']}{block}_01.pdf",
                    cache / f"{block}.pdf")
        lines = pdf_lines(pdf)
        series = series_numbers(lines)
        for num, stem, texts in parse_block(lines):
            stats["total"] += 1
            qid = f"{letter}{num:03d}"
            body = stem + "".join(texts)

            if num in series:
                # 症例文を共有する連問。設問文だけでは成立しないため取り込まない。
                stats["series"] += 1
                continue
            if IMAGE_REF.search(body):
                stats["image"] += 1
                continue
            if FIGURE_REF.search(body) and len(body) < FIGURE_REF_MIN_BODY:
                # 参照先の図表が本文に入っておらず、設問だけでは解けない。
                stats["image"] += 1
                continue
            if MULTI_SELECT.search(body):
                stats["multi"] += 1
                continue
            if is_unusable(body) or has_broken_glyph(body):
                # PDFのグリフを解決できず本文が欠けている／別の字に化けている。
                # そのまま表示すると誤読の原因になるので落とす。
                stats["cid"] += 1
                continue
            if not TRUSTWORTHY_STEM.search(stem) or BAD_STEM_START.match(stem):
                # 設問文の切り出しに失敗している。前の設問の途中から始まって
                # いたり、受験上の注意ページの表が紛れ込んだりしたもの。
                stats["bad_stem"] += 1
                continue
            seen[qid] = seen.get(qid, 0) + 1

            ans = answers.get(qid, [])
            if len(ans) != 1 or not re.fullmatch(r"[A-E]", ans[0]):
                # 複数正答・計算問題・採点除外問題
                stats["no_answer"] += 1
                continue
            key = ans[0]

            stem = normalize(stem)
            texts = [normalize(t) for t in texts]
            if len(set(texts)) != len(texts) or any(not t for t in texts):
                stats["bad_choices"] += 1
                continue

            correct_text = texts[CHOICE_KEYS.index(key)]
            questions.append({
                "id": f"k{args.exam}-{qid}",
                "exam_type": "KOKUSHI",
                "question_type": "M",
                "blueprint_code": f"{args.exam}-{letter}-{num}",
                "category": classify(stem + "".join(texts)),
                "difficulty": "standard",
                "question_text": stem,
                "choices": [{"id": k, "text": t}
                            for k, t in zip(CHOICE_KEYS, texts, strict=True)],
                "correct_choice_id": key,
                "explanation": build_explanation(args.exam, letter, num, key,
                                                 correct_text, cfg["page"]),
                "source_note": (
                    f"出典：厚生労働省ホームページ 第{args.exam}回医師国家試験 "
                    f"{letter}{num:03d}（{cfg['page']}）"
                    "／設問文および選択肢を本アプリの表示形式に整形"
                ),
            })
            stats["ok"] += 1

    # 同じ設問番号を2回以上拾っていたら、どれが本物か決められない。片方は
    # 切り出しの誤りなので、番号ごと落とす（誤った本文を出すよりは減らす）。
    dupes = {qid for qid, n in seen.items() if n > 1}
    if dupes:
        keep = [q for q in questions if q["id"].split("-")[-1] not in dupes]
        stats["duplicate"] = len(questions) - len(keep)
        stats["ok"] = len(keep)
        questions = keep

    batch = {
        "meta": {
            "generated_at": "",
            "generator": "mhlw-kokushi-import",
            "blueprint_version": f"kokushi-{args.exam}",
            "batch_id": f"kokushi{args.exam}",
            "source": cfg["page"],
            "license": "Public Data License 1.0 (厚生労働省ホームページ)",
        },
        "questions": questions,
        "question_sets": [],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    print(f"抽出設問       : {stats['total']}")
    print(f"  連問で除外     : {stats['series']}")
    print(f"  別冊参照で除外 : {stats['image']}")
    print(f"  複数選択で除外 : {stats['multi']}")
    print(f"  正答が単一でない: {stats['no_answer']}")
    print(f"  抽出欠損で除外 : {stats['cid']}")
    print(f"  設問文不備で除外: {stats['bad_stem']}")
    print(f"  番号重複で除外 : {stats['duplicate']}")
    print(f"  選択肢不備で除外: {stats['bad_choices']}")
    print(f"取り込み        : {stats['ok']}")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
