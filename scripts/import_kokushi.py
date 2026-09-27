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

第106〜116回はさらに厄介で、PDFが名乗る文字そのものが誤っている。数字・
括弧・一部の漢字が ToUnicode では空白や U+FFFD に、pdfplumber の既定の符号表
では別の記号や数字になり（"蛋白8−:"、"紫斑病=ITP>"、"糖:−<"）、読める字の
形をしているため網に掛からず公開まで残っていた。

そこで次の順に解決し、決まらなかった文字を含む設問は取り込まない。

0. 埋め込みフォントから字形（輪郭）を取り出し、目視で同定した字形の表
   （GLYPH_OUTLINES）にあればその字にする。ほかのどの解決よりも優先し、
   表に無い字形なのにPDFが文字を名乗っていなければ解決できなかったとみなす。
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
  ｆ 以降まである設問（6択以上）もここで落とす。

使い方
------
    for e in 119 118 117 116 115 114 113 112 111 110 109 108 107 106; do
        python scripts/import_kokushi.py --exam $e \
            --out backend/quiz/management/commands/data/kokushi_$e.json
    done
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

# 同梱データの検査（backend/tests/test_shipped_data.py）と同じ正規表現を使い、
# 検査で落ちる設問は取り込みの時点で落とす。quiz.data_checks は正規表現だけで
# Django に依存しない。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from quiz.data_checks import (  # noqa: E402
    BODY_KANJI_AFTER_DIGIT,
    BRACKET_LOOKALIKE,
    DECODE_ARTIFACT,
    DROPPED_NUMBER,
    DROPPED_WORD_HEAD,
    GLYPH_CORRUPTION,
    KANJI_DIGIT_KANJI,
    POSITION_KANJI_THEN_LATIN,
    STRAY_SEPARATOR,
    strip_stray_separators,
)

try:
    import pdfplumber
except ImportError:  # pragma: no cover - 実行環境の案内
    sys.exit(
        "pdfplumber が必要です: pip install -r requirements-scripts.txt\n"
        "（pypdf は本PDFのフォント埋め込みを解決できず文字化けするため使わないこと）"
    )

# 回ごとの公開ページとPDF。厚労省は回ごとにURLも命名も変わるため表で持つ。
# 回を足すときは、公開ページの href と各PDFの表紙（「指示があるまで開かない
# こと。」の下の「107 Ｅ」など）で、どれがどのブロックの問題冊子かを確かめる
# こと。推測すると404になるか、別冊（画像）や別のブロックを読んでしまう。
#  - 第117回はページが tp230502-01.html なのに PDF は tp220502-01*.pdf。
#  - 第107・108回は a〜s の連番で、問題冊子（a,c,e,…,q）と別冊（b,d,…,r）が
#    交互に並び、s が正答値表。
#  - 第106回は tp_siken_106_ishi_{a〜i}1.pdf が問題冊子、無印が正答値表。
#  - 第111回までは500問（A〜I の9ブロック）、第112回からは400問（A〜F）。
#  - 第105回以前のPDFは紙をスキャンした画像で文字が入っていない。読み取り
#    （OCR）は字を取り違えるので扱わない。
_BASE = "https://www.mhlw.go.jp/seisakunitsuite/bunya/kenkou_iryou/iryou/topics"
_DL = f"{_BASE}/dl"


def _standard(page: str, prefix: str, letters: str) -> dict:
    """第109回以降の命名。問題冊子が {prefix}{a}_01.pdf、正答値表が {prefix}seitou.pdf。"""
    return {
        "page": f"{_BASE}/{page}",
        "answers": f"{_DL}/{prefix}seitou.pdf",
        "blocks": {c.upper(): f"{_DL}/{prefix}{c}_01.pdf" for c in letters},
    }


def _alternating(page: str, prefix: str) -> dict:
    """第107・108回。問題冊子と別冊が交互に並び、最後の s が正答値表。"""
    return {
        "page": f"{_BASE}/{page}",
        "answers": f"{_DL}/{prefix}s.pdf",
        "blocks": {b: f"{_DL}/{prefix}{c}.pdf" for b, c in zip("ABCDEFGHI", "acegikmoq")},
    }


_TOPICS_2012 = "https://www.mhlw.go.jp/topics/2012/04"

EXAMS = {
    119: _standard("tp250428-01.html", "tp250428-01", "abcdef"),
    118: _standard("tp240424-01.html", "tp240424-01", "abcdef"),
    117: _standard("tp230502-01.html", "tp220502-01", "abcdef"),
    116: _standard("tp220421-01.html", "tp220421-01", "abcdef"),
    115: _standard("tp210416-01.html", "tp210416-01", "abcdef"),
    114: _standard("tp200421-01.html", "tp200421-01", "abcdef"),
    113: _standard("tp190415-01.html", "tp190415-01", "abcdef"),
    112: _standard("tp180511-01.html", "tp180511-01", "abcdef"),
    111: _standard("tp170425-01.html", "tp170425-01", "abcdefghi"),
    110: _standard("tp160411-01.html", "tp160411-01", "abcdefghi"),
    109: _standard("tp150511-01.html", "tp150511-01", "abcdefghi"),
    108: _alternating("tp140512-01.html", "tp140512-01"),
    107: _alternating("tp130723-01.html", "tp130723-01"),
    106: {
        "page": f"{_TOPICS_2012}/tp0420-01.html",
        "answers": f"{_TOPICS_2012}/dl/tp_siken_106_ishi.pdf",
        "blocks": {c.upper(): f"{_TOPICS_2012}/dl/tp_siken_106_ishi_{c}1.pdf"
                   for c in "abcdefghi"},
    },
}

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

# 1ブロックの設問数の上限（A/C/D/F が75問、B/E が50問）。これを超える
# 数字はページ端の数字なので設問番号として扱わない。
MAX_Q_NO = 75
# 除外された設問があると番号が飛ぶので、直前の番号のすぐ次だけでなく
# 少し先まで候補にする。
LOOKAHEAD = 5

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


# 第109回のPDFには版下の情報（"TP01doc-Aor-11" と "山田山企画-医師-本冊Ａ2.indd
# 11 — 2014/12/23 9:42"）が本文として残っていて、直前に数字だけの行（台紙の
# 通し番号）が付く。ページ末の設問では最後の選択肢にそのままつながり、
# 「…有用である。1 TP01doc-Aor-11山田山企画…」になっていた。
SLUG_LINE = re.compile(r"^TP\d+doc-|\.indd\b")


def _clean(lines: list[str]) -> list[str]:
    out = []
    for i, ln in enumerate(lines):
        if NOISE_LINE.search(ln) or SLUG_LINE.search(ln):
            continue
        if re.fullmatch(r"\s*\d{1,3}\s*", ln) and i + 1 < len(lines) and SLUG_LINE.search(lines[i + 1]):
            continue
        out.append(ln.rstrip())
    return out


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
    "粟": "↓", "或": "→", "袷": "+", "安": "−", "庵": "×", "案": "±", "鮎": "↑",
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
        try:
            page.set_cropbox(page.mediabox)
        except ValueError:
            # 第106・107回の正答値表は MediaBox の原点が (0,0) でなく
            # （[-14.2 14.17 711.8 1040.9]）、PyMuPDF はこれを CropBox に
            # 設定できない。CropBox は元から MediaBox と同じなのでそのまま使う。
            # 座標がずれていれば突き合わせが減って設問が落ちるだけで、誤読は増えない。
            pass

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


# --- 字形で決める --------------------------------------------------------
#
# 上の解決はどれも「PDFが名乗る文字」を頼りにしている。ところが第106〜116回の
# PDFには、名乗る文字そのものが誤っているフォントが混ざっていた。数字・括弧・
# 一部の漢字が、ToUnicode では空白や U+FFFD に、pdfplumber が代わりに使う
# 既定の符号表では無関係な記号や別の数字になる。
#
#   "尿所見:蛋白8−:、糖8−:"          正しくは 蛋白（−）、糖（−）   第106回
#   "特発性血小板減少性紫斑病=ITP>"    正しくは 〈ITP〉              第106回
#   "SpO2 99%:マスク L/分酸素投与下<"  括弧が化け、数字も欠けている   第114回
#   "両下)の浮腫"                      正しくは 両下腿（グリフ名の誤り） 第116回
#   "レニン活性鮎"                     正しくは ↑                   第110回
#   "c-GTP"、"b遮断薬"                 正しくは γ-GTP、β遮断薬      第109回
#
# どれも読める文字なので、字化けの網（has_broken_glyph や data_checks の検査）
# には掛からない。第114〜116回はこのまま公開されていた。
#
# そこでPDFに埋め込まれたフォントから字形（輪郭）を取り出し、輪郭で文字を
# 決める。GLYPH_OUTLINES は第106〜119回の全PDFを調べ、PDFが文字を名乗って
# いない字形（空白・U+FFFD・制御文字なのに輪郭がある）と、小さな記号・数式
# フォントの全字形を描画して、目視で同定した表（輪郭の指紋 -> 文字）である。
# 確かさは2通りで確かめた。
#
#   - 同じ字形を /Differences のグリフ名（CID_GLYPHS）からも復元できる箇所が
#     約1万7千あり、2種類11か所を除いてすべて一致した。食い違った11か所は
#     グリフ名のほうが誤っていた（上の「両下)」と、「末梢」が「末這」）。
#   - 第106〜119回で使われる約6千の字形について、同じ輪郭が回やフォントを
#     またいでも同じ文字になることを確かめた。
#
# 輪郭で決まった文字は、ほかのどの解決よりも優先する。表に無い字形なのに
# PDFが文字を名乗っていないものは UNRESOLVED にして設問ごと落とす（抽出器が
# 補った字には根拠がない）。回を足して落ちる設問が増えたら、その字形を描画して
# 表に足すこと。

# 輪郭の指紋 -> 文字。指紋は _outline_key() で作る。コメントは、その字形が
# 現れる回と、PDFがその字形に名乗らせていた文字（ToUnicode・PyMuPDF 側）。
# 同じ字でも書体（明朝・ゴシック）や回によって輪郭が違うので行が分かれる。
GLYPH_OUTLINES: dict[str, str] = {
    # 数字
    "7f20a8629e99eeda": "0",  # 第106〜107回（PDFの文字: U+FFFD）
    "66dc771da508278b": "0",  # 第106〜107・110〜116回（PDFの文字: U+FFFD空白）
    "7ccc056f3bd46406": "1",  # 第106〜107・110〜112・114〜116回（PDFの文字: U+FFFD）
    "177161704ae99410": "1",  # 第106〜107・116回（PDFの文字: U+FFFD）
    "a6574813217e75f4": "1",  # 第113回（PDFの文字: 空白）
    "d8809526e299bde3": "2",  # 第106〜107・110〜112・114〜116回（PDFの文字: U+FFFD）
    "a7c9069d96e2cd6c": "2",  # 第106〜107・110〜116回（PDFの文字: U+FFFD઄）
    "330b3eb510f22460": "2",  # 第113回（PDFの文字: 空白）
    "e132d83c2bb91b7f": "3",  # 第106〜107・110〜116回（PDFの文字: U+FFFD空白）
    "66f57bd54f46225c": "3",  # 第106〜107・110〜116回（PDFの文字: U+FFFDઅ）
    "1124215129019025": "4",  # 第106〜107・110〜112・114〜116回（PDFの文字: U+FFFD）
    "4273ece882bb153c": "4",  # 第110〜112・114〜116回（PDFの文字: U+FFFD）
    "d376f3d6c94cc578": "4",  # 第113回（PDFの文字: 空白）
    "d9f81f69b3393974": "4",  # 第113回（PDFの文字: આ）
    "68880704ff6c480b": "5",  # 第106〜107・110〜116回（PDFの文字: U+FFFD空白）
    "2be56a5396ecff9d": "5",  # 第115〜116回（PDFの文字: U+FFFD）
    "ea66f398b520d277": "6",  # 第106〜107・110〜116回（PDFの文字: U+FFFD空白）
    "b04a4df2a0da3164": "6",  # 第112・116回（PDFの文字: U+FFFD）
    "03299fb0a3550699": "7",  # 第106〜107・110〜116回（PDFの文字: U+FFFD空白）
    "b0c5b4764fbb8832": "8",  # 第106〜107・110〜116回（PDFの文字: U+FFFD空白）
    "38b328767d744ad5": "8",  # 第106〜107・112・116回（PDFの文字: U+FFFD）
    "8dece395412f7788": "9",  # 第106〜107・110〜116回（PDFの文字: U+FFFD空白）
    # 括弧
    "997fcc9d90f4f342": "（",  # 第106〜107・110〜112・114〜116回（PDFの文字: U+FFFD(）
    "0dfa4da2caceb4da": "（",  # 第110〜112回（PDFの文字: U+FFFD）
    "f40f503cf3947267": "（",  # 第113回（PDFの文字: 空白;(）
    "258009818a349c75": "）",  # 第106〜107・110〜116回（PDFの文字: U+FFFD空白=)）
    "0af4d765434427fe": "）",  # 第110〜112回（PDFの文字: U+FFFD）
    "c184abb9f578e005": "〈",  # 第106〜107・110〜112・114〜116・119回（PDFの文字: U+FFFD〈）
    "f827fd52b2d9119c": "〈",  # 第113回（PDFの文字: ÜôÎìJ空白）
    "5eeeea659053af5c": "〉",  # 第106〜107・109〜112・114〜119回（PDFの文字: U+FFFD〉）
    "775d642f4908ab5c": "〉",  # 第113回（PDFの文字: Þý×íO空白）
    "22ee6c1a4b1c4814": "[",  # 第107・110〜112・114〜116回（PDFの文字: U+FFFD[）
    "bd322c4ee928c7ff": "]",  # 第107・110〜112・114〜116回（PDFの文字: U+FFFD]）
    "d3678b139776c5a8": "『",  # 第112・116回（PDFの文字: U+FFFD）
    "ca52fe66189936ba": "』",  # 第112・116・119回（PDFの文字: U+FFFD』）
    "99666cc0e17bfb97": "【",  # 第113回（PDFの文字: ò）
    "ba0aebe59f0dfa75": "【",  # 第114回（PDFの文字: U+FFFD）
    "c911934ff4411934": "】",  # 第113回（PDFの文字: ø）
    "a86897e82e804e11": "】",  # 第114回（PDFの文字: U+FFFD）
    # 漢字
    "bad2524edfa4acad": "XIII",  # 第106・112・114・117回（PDFの文字: U+FFFDX）
    "3486298d5f159ce6": "倦",  # 第106〜107・109〜119回（PDFの文字: U+FFFD倦.S4）
    "e25e87ffb95d1c38": "屑",  # 第113回（PDFの文字: ×）
    "f800b85915a6537b": "扁",  # 第106〜107・109〜112・114〜119回（PDFの文字: U+FFFD扁）
    "cfb3205eb634548d": "扁",  # 第113回（PDFの文字: 空白）
    "11f55d39d359809e": "梢",  # 第106〜107・109〜112・114〜119回（PDFの文字: U+FFFD梢）
    "d048c32fbde5e086": "梢",  # 第113回（PDFの文字: ¢Î*9:）
    "e8b80578a40f4ac2": "溢",  # 第110回（PDFの文字: U+FFFD）
    "439245d803c6f6a7": "牙",  # 第111・115回（PDFの文字: U+FFFD）
    "9cc661adaaa2be96": "疼",  # 第106〜107・110〜112・114〜119回（PDFの文字: U+FFFD疼）
    "c1200039eb0fad1e": "疼",  # 第113回（PDFの文字: 空白）
    "b527bac3df8e5817": "穿",  # 第106〜107・109〜119回（PDFの文字: U+FFFD穿空白）
    "7d0e686693e3bb13": "腔",  # 第107回（PDFの文字: U+FFFD）
    "fa545558f9b3612f": "腿",  # 第107・109〜112・114〜119回（PDFの文字: U+FFFD腿）
    "c949366377ea9fd6": "腿",  # 第113回（PDFの文字: üdwSU+FFFD&）
    "25a31084d4035582": "這",  # 第111〜112・116・119回（PDFの文字: U+FFFD這）
    "134d6cc684a44471": "這",  # 第113回（PDFの文字: .）
    "2dd287446448c2f9": "鞘",  # 第106〜107・109〜110・116・118回（PDFの文字: U+FFFD鞘）
    # 記号
    "95d6a1d5a6fc5713": "↓",  # 第106〜107・110〜112・114〜117回（PDFの文字: 粟）
    "a87dbaf4aa899ef8": "↓",  # 第113回（PDFの文字: 粟）
    "352794308f0ec503": "→",  # 第106〜107・110〜112・114〜119回（PDFの文字: 或→）
    "5e45a6b6a88bebbb": "→",  # 第113回（PDFの文字: 或）
    "c7af2eb23d90de3d": "−",  # 第106〜107・110〜112・114〜116回（PDFの文字: 安）
    "4a00a77208947bda": "−",  # 第113回（PDFの文字: 安）
    "3e73fbb5c6ae7663": "+",  # 第106〜107・110〜112・114〜116回（PDFの文字: 袷）
    "ffcb0d3ce4ab335e": "+",  # 第113回（PDFの文字: 袷）
    "f9844656991023f4": "±",  # 第106〜107・110〜112・114〜115回（PDFの文字: 案）
    "f7d794f04718184c": "±",  # 第109回（PDFの文字: !）
    "b8aaab3b85bc6d5b": "±",  # 第113回（PDFの文字: 案）
    "2e0712b2b4935405": "×",  # 第106〜107・110〜112・114〜116回（PDFの文字: 庵）
    "c3e30acc1e4bac44": "×",  # 第109回（PDFの文字: #×）
    "7fe90e7823433560": "×",  # 第113回（PDFの文字: 庵）
    "f57c01e408fb1f4f": "↑",  # 第110回（PDFの文字: 鮎）
    "50ce59fa429f3c91": "=",  # 第113回（PDFの文字: 暗）
    # ギリシャ文字（第109回の数式フォント）
    "ac0e3150571100af": "α",  # 第109回（PDFの文字: a）
    "a70df77541ca86b0": "α",  # 第109回（PDFの文字: a）
    "1b5694b85d9b5e3e": "β",  # 第109回（PDFの文字: b）
    "e4f0d76e3a5ec413": "β",  # 第109回（PDFの文字: b）
    "656a8eacdfa8ff96": "γ",  # 第109回（PDFの文字: c）
    "41f56932c7a113af": "γ",  # 第109回（PDFの文字: c）
    "97f652f4298ba519": "μ",  # 第109回（PDFの文字: n）
    "e6baf5911d7aa279": "μ",  # 第109回（PDFの文字: n）
}

# フォントの読み込みで fontTools が出す警告（"'created' timestamp out of
# range" など）は字形に関係しないので黙らせる。
logging.getLogger("fontTools").setLevel(logging.ERROR)


def _outline_key(commands: list) -> str:
    """輪郭（fontTools の RecordingPen の記録）の指紋。輪郭が無ければ ""。

    座標を 0.1 単位に丸めて文字列にし、SHA-1 の先頭16桁を取る。同じ書体の
    同じ字なら、部分集合や回が違っても同じ指紋になる。
    """
    if not commands:
        return ""
    shape = tuple(
        (op, tuple(tuple(round(float(v), 1) for v in pt) for pt in args if pt is not None))
        for op, args in commands
    )
    return hashlib.sha1(repr(shape).encode()).hexdigest()[:16]


def _load_glyphs(doc, xref: int):
    """埋め込みフォントから、グリフ番号 -> 字形 を引く関数を作る。読めなければ None。"""
    from fontTools.cffLib import CFFFontSet
    from fontTools.ttLib import TTFont

    try:
        _name, ext, _type, buf = doc.extract_font(xref)
        if not buf:
            return None
        if ext in ("ttf", "otf"):
            font = TTFont(io.BytesIO(buf))
            order = font.getGlyphOrder()
            glyph_set = font.getGlyphSet()
            return lambda gid: glyph_set[order[gid]] if 0 <= gid < len(order) else None
        if ext in ("cff", "cid"):
            cff = CFFFontSet()
            cff.decompile(io.BytesIO(buf), None)
            top = cff[cff.fontNames[0]]
            strings = top.CharStrings
            order = top.getGlyphOrder()
            if hasattr(top, "ROS"):
                # CIDで引く形式のCFF。MuPDF はCIDをそのままグリフ番号として返す。
                by_cid = {int(n[3:]) if n.startswith("cid") else gid: n
                          for gid, n in enumerate(order)}
                return lambda cid: strings[by_cid[cid]] if cid in by_cid else None
            return lambda gid: strings[order[gid]] if 0 <= gid < len(order) else None
    except Exception:  # 壊れたフォントは字形で決めないだけ
        return None
    return None


class _GlyphShapes:
    """PDF1冊ぶんの、(フォントの xref, グリフ番号) -> 輪郭の指紋。"""

    def __init__(self, doc):
        self.doc = doc
        self.fonts: dict[int, object] = {}
        self.keys: dict[tuple[int, int], str | None] = {}

    def key(self, xref: int, gid: int) -> str | None:
        """指紋。輪郭が無ければ ""、フォントやグリフが読めなければ None。"""
        from fontTools.pens.recordingPen import RecordingPen

        if (xref, gid) not in self.keys:
            if xref not in self.fonts:
                self.fonts[xref] = _load_glyphs(self.doc, xref)
            lookup = self.fonts[xref]
            glyph = lookup(gid) if lookup else None
            key = None
            if glyph is not None:
                pen = RecordingPen()
                try:
                    glyph.draw(pen)
                    key = _outline_key(pen.value)
                except Exception:
                    key = None
            self.keys[(xref, gid)] = key
        return self.keys[(xref, gid)]


def _page_shapes(page, shapes: _GlyphShapes) -> list[tuple]:
    """1ページの字を PyMuPDF で見たもの。

    (x0, x1, y0, 原点x, 原点y, 名乗る文字, 字形で決めた文字) の並び。
    字形で決めた文字は、GLYPH_OUTLINES にあればその字、表に無い字形なのに
    PDFが文字を名乗っていなければ UNRESOLVED、それ以外は None（名乗る文字
    のままでよい）。
    """
    programs: dict[str, set[int]] = {}
    for font in page.get_fonts():
        programs.setdefault(re.sub(r"^[A-Z]{6}\+", "", font[3]), set()).add(font[0])
    out = []
    for span in page.get_texttrace():
        xrefs = programs.get(span["font"], ())
        for uc, gid, origin, bbox in span["chars"]:
            ch = chr(uc) if uc >= 0 else UNRESOLVED
            # 同じ名前のフォントが複数あって字形が食い違うときは決めない
            keys = {shapes.key(xref, gid) for xref in xrefs}
            key = keys.pop() if len(keys) == 1 else None
            out.append((bbox[0], bbox[2], bbox[1], origin[0], origin[1], ch, shape_decision(ch, key)))
    return out


def shape_decision(ch: str, key: str | None) -> str | None:
    """PDFが名乗る文字 ch と字形の指紋 key から、使う文字を決める。

    表にある字形ならその字。表に無い字形なのに、PDFが文字を名乗っていない
    （空白・U+FFFD・制御文字なのに輪郭がある）なら UNRESOLVED。フォントが
    読めず字形が分からない（key が None）ときは、U+FFFD と制御文字だけを
    UNRESOLVED にし、空白は空白のままにする。それ以外は None（名乗るとおり）。
    """
    if key and key in GLYPH_OUTLINES:
        return GLYPH_OUTLINES[key]
    blank = ch in (" ", "\u3000")
    unnamed = blank or ch == UNRESOLVED or unicodedata.category(ch) in _UNUSABLE_CATEGORIES
    if unnamed and (key or (key is None and not blank)):
        return UNRESOLVED
    return None


def _shape_fixes_by_origin(doc) -> list[dict[tuple[float, float], list[str | None]]]:
    """PyMuPDF で読むとき用。ページごとに 字の原点 -> 字形で決めた文字の列。

    「）（」のように同じ原点に2字が描かれることがあるので、原点ごとに描画の
    順で並べておき、_take_shape_fix() で前から1つずつ取り出す。
    """
    shapes = _GlyphShapes(doc)
    pages = []
    for page in doc:
        fixes: dict[tuple[float, float], list[str | None]] = {}
        for rec in _page_shapes(page, shapes):
            fixes.setdefault((round(rec[3], 1), round(rec[4], 1)), []).append(rec[6])
        pages.append(fixes)
    return pages


def _take_shape_fix(ch: dict, fixes: dict[tuple[float, float], list[str | None]]) -> str | None:
    """rawdict の1文字に対応する、字形で決めた文字（無ければ None）。"""
    queue = fixes.get((round(ch["origin"][0], 1), round(ch["origin"][1], 1)))
    return queue.pop(0) if queue else None


def _shape_fixes(path: Path) -> list[dict[int, str]]:
    """pdfplumber で読むとき用。ページごとに page.chars の添字 -> 字形で決めた文字。

    pdfplumber の文字は字形を持たないので、PyMuPDF で見た字と座標で突き合わせる
    （_crossref_table と同じく y のずれを中央値で求める）。

    - 左端だけで合わせると取り違える。和文の「（」は字面の左側が空いていて、
      直前の半角数字と左端が重なる（"8,900（桿状核" の 0 と （ が同じ x0）。
      右端まで合わせる。
    - 「）（」と続くところは2字がまったく同じ枠に描かれていて、座標では
      区別できない。どちらの抽出器も描画の順に字を返すので、1つの字には
      1つの字形だけを割り当て、同じ近さなら順番どおりに組にする。

    突き合わせられなかった字は、同じフォントの同じ符号が突き合わせられた
    箇所の結果に従う。そこで結果が割れていれば決めずに UNRESOLVED にする。
    """
    import pymupdf

    doc = pymupdf.open(path)
    for page in doc:
        try:
            page.set_cropbox(page.mediabox)
        except ValueError:
            pass  # _crossref_table と同じ（第106・107回の正答値表）
    shapes = _GlyphShapes(doc)

    result: list[dict[int, str]] = []
    learned: dict[tuple[str, str], set[str | None]] = {}
    unaligned: list[tuple[int, int, tuple[str, str]]] = []
    with pdfplumber.open(path) as pdf:
        for pno, plumber_page in enumerate(pdf.pages):
            fixes: dict[int, str] = {}
            result.append(fixes)
            mu = _page_shapes(doc[pno], shapes) if pno < doc.page_count else []
            by_x: dict[float, list[int]] = {}
            for n, rec in enumerate(mu):
                by_x.setdefault(round(rec[0], 1), []).append(n)
            chars = plumber_page.chars
            deltas = sorted(
                mu[n][2] - ch["top"]
                for ch in chars
                for n in by_x.get(round(ch["x0"], 1), ())
                if mu[n][5] == ch["text"]
            )
            dy = deltas[len(deltas) // 2] if deltas else None
            pairs: list[tuple[float, int, int]] = []
            if dy is not None:
                for i, ch in enumerate(chars):
                    x = round(ch["x0"], 1)
                    for bx in (x - 0.1, x, x + 0.1):
                        for n in by_x.get(round(bx, 1), ()):
                            rec = mu[n]
                            dist = abs(rec[2] - dy - ch["top"])
                            if dist >= 1.0 or abs(rec[0] - ch["x0"]) >= 0.15:
                                continue
                            dist += abs(rec[0] - ch["x0"]) + abs(rec[1] - ch["x1"])
                            pairs.append((round(dist, 3), i, n))
            matched: dict[int, int] = {}
            used: set[int] = set()
            for _dist, i, n in sorted(pairs):
                if i not in matched and n not in used:
                    matched[i] = n
                    used.add(n)
            for i, ch in enumerate(chars):
                ident = (ch["fontname"], ch["text"])
                if i not in matched:
                    unaligned.append((pno, i, ident))
                    continue
                fixed = mu[matched[i]][6]
                learned.setdefault(ident, set()).add(fixed)
                if fixed is not None:
                    fixes[i] = fixed
    doc.close()

    for pno, i, ident in unaligned:
        seen = learned.get(ident)
        if not seen or seen == {None}:
            continue
        result[pno][i] = next(iter(seen)) if len(seen) == 1 else UNRESOLVED
    return result


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


# 欧文の語間。国試PDFの英文は空白の字を持たず、語と語の間を 0.3em ほど
# （10pt で約3pt）空けて組んであるだけで、extract_text() の既定の閾値（3pt）を
# わずかに下回る。そのため "The patient felt faint" が "Thepatientfeltfaint"
# に、"room air" が "roomair" になっていた。語の中の字間は 0 なので、英字の
# 手前が 0.15em 以上空いていれば空白を補う。和文や数字の前後は対象にしない
# （"40歳" "SpO298%" の組み方は変えない）。
#
# 見かけの隙間には語間でないものが2つ混ざる。
#   - 添字や、ベースラインが少しずれた字が隙間に描かれている（"mmH2O" の 2、
#     "FIO2" の I、第113回の "MRI" の R は 0.6pt 高い）。行の組み分けで別の
#     行に入り、隣どうしに見えてしまう。隙間に字があれば語間ではない。
#   - 字間を広げて組んだ行（第117回の "Na 136mEq/L" は字ごとに 1.6pt 空く）。
#     その行の英字どうしの字間の中央値の2倍に届かなければ語間ではない。
# また "/" を含む単位のあと（"8.7g/gCr"）は、隙間があっても1つの単位として続ける。
WORD_GAP_EM = 0.15
_WORD_END = re.compile(r"[A-Za-z.,;:'’\")]")
_WORD_START = re.compile(r"[A-Za-z]")


def _line_key(ch: dict) -> int:
    return round(ch["top"] / LINE_Y_TOLERANCE)


def _word_gaps(ordered: list[dict]) -> set[int]:
    """ordered（行ごと・左から）のうち、手前に語間の空白を補う字の添字。"""
    tracking: dict[int, float] = {}
    lines: dict[int, list[dict]] = {}
    for ch in ordered:
        lines.setdefault(_line_key(ch), []).append(ch)
    for key, line in lines.items():
        gaps = sorted(
            b["x0"] - a["x1"] for a, b in zip(line, line[1:])
            if _WORD_START.fullmatch(a["text"]) and _WORD_START.fullmatch(b["text"])
        )
        tracking[key] = gaps[len(gaps) // 2] if gaps else 0.0

    def occupied(left: dict, right: dict) -> bool:
        for key in (_line_key(right) - 1, _line_key(right), _line_key(right) + 1):
            for other in lines.get(key, ()):
                if (other is not left and other is not right
                        and abs(other["top"] - right["top"]) < LINE_Y_TOLERANCE
                        and other["x1"] > left["x1"] + 0.1 and other["x0"] < right["x0"] - 0.1):
                    return True
        return False

    starts: set[int] = set()
    for i in range(1, len(ordered)):
        prev, ch = ordered[i - 1], ordered[i]
        if _line_key(prev) != _line_key(ch):
            continue
        if not (_WORD_END.fullmatch(prev["text"]) and _WORD_START.fullmatch(ch["text"])):
            continue
        gap = ch["x0"] - prev["x1"]
        if gap < max(WORD_GAP_EM * ch["size"], 2 * tracking[_line_key(ch)]) or gap > COLUMN_GAP:
            continue
        if occupied(prev, ch) or "/" in _word_before(ordered, i):
            continue
        starts.add(i)
    return starts


def _word_before(ordered: list[dict], i: int) -> str:
    """ordered[i] の手前に隙間なく続いている字（同じ行の、字間 0.5pt 未満）。"""
    word = []
    k = i - 1
    while k >= 0 and _line_key(ordered[k]) == _line_key(ordered[i]):
        word.append(ordered[k]["text"])
        if k == 0 or ordered[k]["x0"] - ordered[k - 1]["x1"] >= 0.5:
            break
        k -= 1
    return "".join(reversed(word))


def _with_column_separators(chars: list[dict]) -> list[dict]:
    """左右2列に組まれた箇所へ区切りを、欧文の語間へ空白を差し込む。

    extract_text() は語を1個の空白でつなぐため、そのままでは列の境目が
    字間と区別できなくなる（"疥 癬 外陰部" が「疥/癬/外陰部」に見える）。
    間隔が空いている箇所に印を入れてから渡す。
    """
    ordered = sorted(chars, key=lambda c: (_line_key(c), c["x0"]))
    word_starts = _word_gaps(ordered)
    out: list[dict] = []
    for i, ch in enumerate(ordered):
        if out:
            prev = out[-1]
            same_line = abs(prev["top"] - ch["top"]) < LINE_Y_TOLERANCE
            if same_line and ch["x0"] - prev["x1"] > COLUMN_GAP:
                mid = (prev["x1"] + ch["x0"]) / 2
                out.append({**prev, "text": COLUMN_SEPARATOR,
                            "x0": mid - 1, "x1": mid + 1})
            elif i in word_starts:
                out.append({**prev, "text": " ", "x0": prev["x1"], "x1": ch["x0"]})
        out.append(ch)
    return out


def _pdfplumber_lines(path: Path) -> list[str]:
    """pdfplumber の行構造のまま、解決できなかったグリフを埋めて返す。

    page.extract_text() は文字単位のフォント情報を捨ててしまうので、
    page.chars を直接直してから同じ抽出関数に渡す。行の切り方は変わらない。
    字形で決まった文字（_shape_fixes）はほかの解決より優先する。
    """
    from pdfplumber.utils import extract_text

    enc = _encoding_tables(path)
    xref = _crossref_table(path)
    shape = _shape_fixes(path)
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages):
            fixes = shape[pno] if pno < len(shape) else {}
            chars = []
            for i, ch in enumerate(page.chars):
                m = _CID_CHAR.match(ch["text"])
                if i in fixes:
                    ch = {**ch, "text": fixes[i]}
                elif m:
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
    shape = _shape_fixes_by_origin(doc)
    out: list[str] = []
    for pno, page in enumerate(doc):
        rows: dict[int, list[tuple[float, str]]] = {}
        for blk in page.get_text("rawdict")["blocks"]:
            for ln in blk.get("lines", []):
                text = "".join(
                    _mupdf_char(ch, sp["font"], enc, shape[pno])
                    for sp in ln["spans"] for ch in sp["chars"]
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


def _mupdf_char(ch: dict, font: str, enc: dict[str, dict[int, str]],
                fixes: dict[tuple[float, float], list[str | None]]) -> str:
    """PyMuPDF の1文字を直す。字形で決まった文字があればそれを使う。

    PyMuPDF は ToUnicode の無いグリフを生のコード（制御文字）で返すので、
    span のフォント名から /Differences を引いて直す。
    """
    fixed = _take_shape_fix(ch, fixes)
    if fixed is not None:
        return fixed
    if is_unusable(ch["c"]):
        return enc.get(font, {}).get(ord(ch["c"]), UNRESOLVED)
    return _fix_symbol_font(font, ch["c"])


def _usable_count(lines: list[str]) -> int:
    """その抽出結果から何問取り出せるかを数える（採用判定用）。"""
    n = 0
    for _num, stem, texts, _interlude in parse_block(lines):
        body = stem + "".join(texts)
        if stem and not is_unusable(body) and not has_broken_glyph(body):
            n += 1
    return n


# pdfplumber が語の途中に挟むダッシュ。「自己免疫— 性膵炎」「誤って— いる」の
# ように、和文の途中へ EM DASH と空白が入る。PyMuPDF の描画には出てこない
# ので抽出側の産物で、和文の組版として現れる形でもない（日本語のダッシュは
# 「——」と重ねるか前後を空ける）。第119回の全6ブロックで38件見つかり、
# 38件とも取り除いた形が PyMuPDF の描画に一致した。
#
# 欧文や数字に挟まる形（「50Torr—、」「第— 3次」）も残るが、そちらは
# 字種の条件を広げると正当なダッシュまで巻き込む。連問の抽出では
# verify_against_pymupdf() で本文ごと照合するので、そこで弾く。
_STRAY_DASH = re.compile(r"(?<=[ぁ-んァ-ヶ一-龥])[—–―][ 　]?(?=[ぁ-んァ-ヶ一-龥])")


def _drop_stray_dash(line: str) -> str:
    return _STRAY_DASH.sub("", line)


def flat_pymupdf_text(path: Path) -> str:
    """照合用に PyMuPDF の描画を空白抜きで1本にしたもの。

    pdfplumber の抽出には字の入れ替わり（「25,000(」が「25,00(0 」になる等）
    が混じることがある。取り出した本文がこちらに含まれるかを見れば、
    そうした壊れ方をまとめて弾ける。
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - 実行環境の案内
        return ""
    try:
        with pymupdf.open(path) as doc:
            # 本文と同じく、字形で決まった文字に置き換えてから比べる。置き換え
            # ないと、数字が空白になっていた第113回では本文だけに数字が戻って
            # 照合が合わなくなる。
            shape = _shape_fixes_by_origin(doc)
            raw = "\n".join(
                "".join(_take_shape_fix(ch, fixes) or ch["c"]
                        for sp in ln["spans"] for ch in sp["chars"])
                for pg, fixes in zip(doc, shape)
                for blk in pg.get_text("rawdict")["blocks"]
                for ln in blk.get("lines", [])
            )
    except Exception:  # pragma: no cover - 壊れたPDFでも取り込みは続ける
        return ""
    # 第114〜116回は PyMuPDF 側が ToUnicode を持たないフォントを読めず、
    # 制御文字を出す（"\x02か月の乳児" の形）。そういう回は基準に使えない
    # ので、照合そのものを行わない。
    if is_unusable(raw):
        return ""
    try:
        return _for_compare(raw)
    except Exception:  # pragma: no cover - 壊れたPDFでも取り込みは続ける
        return ""


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
    plumber = [_drop_stray_dash(ln) for ln in _pdfplumber_lines(path)]
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
        if re.fullmatch(r"[A-I]\d{3}", token):  # 第111回までは I ブロックまで
            current = token
            answers[current] = []
        elif current is not None and re.fullmatch(r"[A-E]+|\d+", token):
            answers[current].append(token)
    return answers


CHOICE_LINE = re.compile(rf"^([{CHOICE_MARKS}])[ 　]+(\S.*)$")

# ｅ より後ろの選択肢（ｆ〜ｉ）。6択以上の設問（第116回F75、第118回F68）は
# 5択の形に入らない。ｅ の続きとして読むと「早産 — 死産届不要ｆ 早産 — 死産届
# 必要」のように2つの選択肢が1つにつながるので、別の選択肢として数えて落とす。
EXTRA_CHOICE_LINE = re.compile(r"^[ｆｇｈｉ][ 　]+(\S.*)$")

# 選択肢の行が折り返しているとみなす長さ（字数）。本文の1行は34〜53字で、
# 選択肢は字下げのぶん短い。
CHOICE_WRAP_MIN = 30


def _starts_interlude(choice_line: str, rest: list[str]) -> bool:
    """ｅ の行（choice_line）のあとの行（rest）が、選択肢の続きでなく次の段落か。

    ｅ の行が折り返していない（短い、または文が「。」で終わっている）うえで、
    続く行が段落の形（長い行、または「。」で終わる1文）のとき。別冊の案内
    （「別冊 No.12」）は今の設問の画像なので、段落として次へ回さない。
    """
    if not rest or IMAGE_REF.search(rest[0]):
        return False
    # 半角の「｣」「｡」で組まれた回があるので、字形をそろえてから文末を見る。
    ends = lambda s: unicodedata.normalize("NFKC", s).endswith(("。", "」"))  # noqa: E731
    choice_ended = len(choice_line) < CHOICE_WRAP_MIN or ends(choice_line)
    paragraph = len(rest[0]) >= CHOICE_WRAP_MIN or ends(rest[0])
    return choice_ended and paragraph and len("".join(rest)) >= CHOICE_WRAP_MIN


# 照合でぶつかる字形の揺れ。NFKC では寄らないものだけをここで潰す。
# 波ダッシュ U+301C は NFKC の対象外だが、PyMuPDF 側は全角チルダ U+FF5E を
# 出し、そちらは NFKC で "~" になるため食い違う（「基準124〜222」で実際に
# ぶつかった）。マイナス記号も同様に複数の字が混ざる。
_COMPARE_MAP = str.maketrans({
    "〜": "~", "～": "~", "∼": "~",
    "−": "-", "–": "-", "—": "-", "‐": "-", "―": "-",
})


def _for_compare(text: str) -> str:
    """照合用の形。空白を落とし、字形の揺れを NFKC で寄せる。

    pdfplumber と PyMuPDF で「〜」(波ダッシュ) と「～」(全角チルダ)、全角と
    半角の括弧などが食い違う。実際に「（基準124〜222）」でぶつかり、
    連問50組のうち35組がここで落ちていた。ここで作るのは比べるための形
    だけで、保存する本文は元のまま。
    """
    flat = unicodedata.normalize("NFKC", re.sub(r"\s+", "", text))
    return flat.translate(_COMPARE_MAP)


def text_in_reference(text: str, reference: str) -> bool:
    """取り出した本文が PyMuPDF の描画にも在るか。

    pdfplumber の抽出には字の入れ替わり（「25,000(」が「25,00(0 」になる等）
    が混じることがある。空白を除いて突き合わせれば、そうした壊れ方を
    まとめて弾ける。参照が取れなかったときは判定しない（True）。

    表の列の間に差し込んだ区切り（COLUMN_SEPARATOR）は PyMuPDF の描画には
    無いので、外してから比べる。外さないと、表を含む症例文（第115回B43の
    尤度比の表など）は中身が正しくても必ず落ちる。
    """
    if not reference:
        return True
    text = re.sub(rf"\s{COLUMN_SEPARATOR}\s", "", text)
    return _for_compare(text) in reference


def series_groups(lines: list[str]) -> dict[int, str]:
    """連問の設問番号 -> 共有する症例文。

    PDFでは
        次の文を読み、47、48の問いに答えよ。
        <症例文>
        47 <設問文>
        ａ …
    の順に並ぶ。症例文は導入行の次から、組の最初の設問番号行の手前まで。

    国試の連問は2問組か3問組で、CBTの四連問（question_sets）とは形が違う。
    症例文を各設問の本文の頭に付けて、1問ずつ解ける独立した設問にする。
    そのままだと設問文だけでは成立せず、これまで丸ごと落としていた
    （第119回で50問、6回ぶんで約300問）。
    """
    groups: dict[int, str] = {}
    for i, line in enumerate(lines):
        m = SERIES_HEAD.search(line)
        if not m:
            continue
        spec = unicodedata.normalize("NFKC", m.group(1))
        nums: set[int] = set()
        for part in re.split(r"[、,]", spec):
            part = part.strip()
            rng = re.fullmatch(r"(\d+)\s*[〜～\-]\s*(\d+)", part)
            if rng:
                nums.update(range(int(rng.group(1)), int(rng.group(2)) + 1))
            elif part.isdigit():
                nums.add(int(part))
        if not nums:
            continue

        first = min(nums)
        body: list[str] = []
        for cont in lines[i + 1 :]:
            mm = Q_START.match(cont)
            if mm and int(mm.group(1)) == first:
                break
            if SERIES_HEAD.search(cont):
                break
            body.append(cont)
        stem = _join_wrapped(body).strip()
        if not stem:
            continue
        for n in nums:
            groups[n] = stem
    return groups


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


def parse_block(lines: list[str]) -> list[tuple[int, str, list[str], str]]:
    """1ブロックの行列から (設問番号, 設問文, 選択肢, 幕間) を切り出す。

    選択肢はふつう5個。ｆ以降がある設問はそれも別の選択肢として返す（取り込みで落とす）。

    幕間は、ｅ の行のあとに続く段落。連問では症例文が設問の間で続くことがあり
    （「その後の経過 ： …」「現症 ： …」）、PDFでは前の設問の ｅ の直後に
    組まれる。ｅ の行が短い（折り返していない）のに長い行が続いていれば、それは
    選択肢の続きではない。どう扱うかは連問の組を知っている main() が決める。

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
    last_num = 0
    for r_i, run in enumerate(runs):
        next_start = runs[r_i + 1][0] if r_i + 1 < len(runs) else len(lines)

        # 各選択肢の本文＝記号行 + 折り返し行（次の記号行の手前まで）
        texts = []
        interlude = ""
        for j, li in enumerate(run):
            stop = run[j + 1] if j + 1 < len(run) else next_start
            parts = [marks[li][1]]
            last = j == len(run) - 1
            extra_seen = False
            for cont in lines[li + 1 : stop]:
                # 次の設問の番号行、または連問の導入文に達したら打ち切る。
                # これを見ないと最後の選択肢が次の症例文を丸ごと飲み込む。
                if Q_START.match(cont) or SERIES_HEAD.search(cont):
                    break
                if _is_choice_line(cont):
                    break
                extra = EXTRA_CHOICE_LINE.match(cont) if last else None
                if extra:
                    texts.append(_join_wrapped(parts))
                    parts = [extra.group(1)]
                    extra_seen = True
                    continue
                parts.append(cont)
            if last and not extra_seen and _starts_interlude(lines[li], parts[1:]):
                interlude = _join_wrapped(parts[1:])
                parts = parts[:1]
            texts.append(_join_wrapped(parts))

        # 設問文＝直前の設問の選択肢が終わってから ａ 行の手前まで
        stem_lines = lines[prev_end : run[0]]
        prev_end = run[-1] + 1

        # 最後の番号行から始める（前問の選択肢の折り返しを巻き込まないため）。
        # ただし番号行に見える行は本物とは限らない。折り返した症例文の
        # 「2 日前から下腹部痛も…」（第119回C44）や、ページ端の「119」
        # 「102」のような数字も同じ形に見える。
        #
        # 設問番号はブロック内で1から順に増え、1ブロックは最大75問なので、
        # 「直前の番号のすぐ次」だけを本物として扱う。単に「直前より大きい」
        # だけにすると、ページ端の 119 のような大きい数字を一度拾った時点で
        # 以降が全部弾かれる（実測で B〜F ブロックが各1〜2問まで落ちた）。
        # 数問続けて落とされることがあるので、少し先まで許す。
        start = None
        for k, line in enumerate(stem_lines):
            m = Q_START.match(line)
            if m and last_num < int(m.group(1)) <= min(last_num + LOOKAHEAD, MAX_Q_NO):
                start = k
        if start is None:
            continue
        stem_lines = stem_lines[start:]

        m = Q_START.match(stem_lines[0])
        num = int(m.group(1))
        last_num = num
        stem = _join_wrapped([m.group(2)] + stem_lines[1:])
        out.append((num, stem, texts, interlude))
    return out


def attach_interludes(parsed, groups: dict[int, str]) -> list[tuple[int, str, list[str], list[str]]]:
    """parse_block の結果に、連問の症例文とその続き（幕間）を割り振る。

    (設問番号, 設問文, 選択肢, 頭に付ける症例文の段落) を返す。連問でなければ
    段落は空。幕間は、同じ症例文の次の設問があるときだけ症例文の続きとして
    後ろの設問に付ける（第114回B43の ｅ のあとの「家族への病歴聴取や…」は
    B44 の症例の一部）。それ以外はこれまでどおり ｅ の続きとして読み、
    落とすかどうかは後段の検査に任せる。幕間を持つ設問自体が落ちても次の
    設問には要るので、検査より先にここで割り振る。
    """
    interludes: dict[str, list[str]] = {}
    out = []
    for num, stem, texts, interlude in parsed:
        case = groups.get(num)
        earlier = list(interludes.get(case, [])) if case is not None else []
        if interlude:
            if case is not None and groups.get(num + 1) == case:
                interludes.setdefault(case, []).append(interlude)
            else:
                texts = texts[:-1] + [_join_wrapped([texts[-1], interlude])]
        out.append((num, stem, texts, [case, *earlier] if case is not None else []))
    return out


def text_defect(stem: str, texts: list[str]) -> str | None:
    """同梱データの検査で落ちる字の化け・欠けがあれば、その種類を返す。

    どれもグリフの解決に失敗した痕跡で、文としては読めてしまうため目視では
    気づけない（「生後4週未満」が「生後週未満」、「〈」が「~」など）。直せる
    かどうかは1問ずつ違うので、取り込みでは落とす。
    """
    for text in [stem, *texts]:
        for name, pattern in (
            ("glyph", GLYPH_CORRUPTION),
            ("kanji_digit", KANJI_DIGIT_KANJI),
            ("kanji_digit", BODY_KANJI_AFTER_DIGIT),
            ("kanji_digit", POSITION_KANJI_THEN_LATIN),
            ("bracket_lookalike", BRACKET_LOOKALIKE),
            ("word_head", DROPPED_WORD_HEAD),
            ("dropped_number", DROPPED_NUMBER),
            ("separator", STRAY_SEPARATOR),
            ("artifact", DECODE_ARTIFACT),
        ):
            if pattern.search(text):
                return name
        for opener, closer in (("(", ")"), ("〈", "〉"), ("「", "」")):
            if text.count(opener) != text.count(closer):
                return "brackets"
        if any("。" in inner for inner in re.findall(r"\(([^()]*)\)", text)):
            return "brackets"
    if "組合せ" in stem and not any("—" in t for t in texts):
        # 左右2列の区切りが入らず、2列が続けて読めてしまう。
        return "combination"
    return None


def excluded_codes(exam: int) -> dict[str, str]:
    """解説の作成時に除外した設問（blueprint_code -> 理由）。

    今の診療に照らして正答が成り立たなくなった設問などを、解説の置き場
    （scripts/kokushi_explanations/）に "exclude" として書いている。取り込み
    直したときにそれらを戻さないように読む。
    """
    path = Path(__file__).resolve().parent / "kokushi_explanations" / f"{exam}.json"
    if not path.exists():
        return {}
    items = json.loads(path.read_text(encoding="utf-8"))
    return {code: body["exclude"] for code, body in items.items() if "exclude" in body}


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


# NFKC は丸数字を裸の数字に変えてしまう（①→1）。第118回F27の選択肢
# 「①2　②5　③3」が「12 25 33」になり、設問が成立しなくなっていた。
# 変換の前後で私用領域に退避させて守る。ローマ数字は逆に半角へ寄せたい
# （「第Ⅷ因子」→「第VIII因子」）ので対象にしない。
_ENCLOSED = {chr(c): chr(0xE000 + c - 0x2460) for c in range(0x2460, 0x2500)}
_ENCLOSED_BACK = {v: k for k, v in _ENCLOSED.items()}


def normalize(text: str) -> str:
    """全角英数字を半角に寄せる。医学用語の全角カナはそのまま残す。"""
    text = "".join(_ENCLOSED.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKC", text)
    return "".join(_ENCLOSED_BACK.get(ch, ch) for ch in text)


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

    seitou = fetch(cfg["answers"], cache / "seitou.pdf")
    answers = parse_answers(pdf_text(seitou))
    print(f"正答値表: {len(answers)} 問")

    questions: list[dict] = []
    seen: dict[str, int] = {}
    stats = {"total": 0, "series": 0, "image": 0, "multi": 0, "cid": 0,
             "bad_stem": 0, "duplicate": 0, "bad_choices": 0, "no_answer": 0,
             "defect": 0, "excluded": 0, "ok": 0}
    excluded = excluded_codes(args.exam)

    for letter, url in cfg["blocks"].items():
        pdf = fetch(url, cache / f"{letter.lower()}.pdf")
        lines = pdf_lines(pdf)
        groups = series_groups(lines)
        reference = flat_pymupdf_text(pdf)
        for num, stem, texts, case_parts in attach_interludes(parse_block(lines), groups):
            stats["total"] += 1
            qid = f"{letter}{num:03d}"

            if case_parts:
                # 症例文を共有する連問。設問文だけでは成立しないので、
                # 症例文（と、前の設問のあとに続いた段落）を頭に付けて
                # 1問ずつ解ける形にする。
                if not all(text_in_reference(t, reference) for t in case_parts):
                    # pdfplumber の抽出に字の入れ替わりなどが混じっている。
                    # 症例文は長く誤りが目立つので、照合できないものは落とす。
                    stats["series"] += 1
                    continue
                stem = "\n".join([*case_parts, stem])

            body = stem + "".join(texts)
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
            if f"{args.exam}-{letter}-{num}" in excluded:
                stats["excluded"] += 1
                continue

            ans = answers.get(qid, [])
            if len(ans) != 1 or not re.fullmatch(r"[A-E]", ans[0]):
                # 複数正答・計算問題・採点除外問題
                stats["no_answer"] += 1
                continue
            key = ans[0]

            stem = normalize(stem)
            texts = [normalize(t) for t in texts]
            if (len(texts) != len(CHOICE_KEYS) or len(set(texts)) != len(texts)
                    or any(not t for t in texts)):
                stats["bad_choices"] += 1
                continue

            # 列区切りの "—" が語の途中に入ったものを直してから検査する。
            stem = strip_stray_separators(stem)
            combination = "組合せ" in stem
            texts = [strip_stray_separators(t, keep_as_separator=combination) for t in texts]
            if text_defect(stem, texts):
                stats["defect"] += 1
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
    print(f"  表記の検査で除外: {stats['defect']}")
    print(f"  解説の作成時に除外: {stats['excluded']}")
    print(f"取り込み        : {stats['ok']}")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
