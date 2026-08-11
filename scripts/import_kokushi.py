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

取り込まないもの
----------------
- 別冊（画像）を参照する問題: 別冊PDFは患者写真等を含み PDL1.0 の対象外に
  なりうるため除外する。厚労省ページ自身も「実際に出題された画像と異なるものが
  あります」と注記している。
- 複数選択（「2つ選べ」等）と計算問題: 現行スキーマが「選択肢ちょうど5個・
  正解1つ」のため入らない。
- 選択肢が ａ〜ｅ の5個そろわないもの: 抽出失敗の可能性があるため落とす。

使い方
------
    python scripts/import_kokushi.py --exam 119 \
        --out backend/quiz/management/commands/data/kokushi_119.json
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
EXAMS = {
    119: {
        "page": "https://www.mhlw.go.jp/seisakunitsuite/bunya/kenkou_iryou/iryou/topics/tp250428-01.html",
        "pdf_base": "https://www.mhlw.go.jp/seisakunitsuite/bunya/kenkou_iryou/iryou/topics/dl",
        "prefix": "tp250428-01",
    },
}

BLOCKS = "abcdef"  # 甲乙丙丁戊己 → 正答表の A〜F に対応

CHOICE_MARKS = "ａｂｃｄｅ"
CHOICE_KEYS = ["A", "B", "C", "D", "E"]

# ページ下部のノンブル。抽出テキストでは "DKIX-0１-AH-2" や、字が二重に
# なった "DDKKIIXX0011AAHH..iinndddd" の形で紛れ込むので、DKIX を含む行を落とす。
NOISE_LINE = re.compile(r"DKIX|DDKKIIXX|^\s*$")

# 別冊（画像）を参照している設問。これらは取り込まない。
IMAGE_REF = re.compile(r"別冊|を別に示す|別に示す")

# 複数選択・計算問題。現行スキーマに入らない。
MULTI_SELECT = re.compile(r"[２2３3４4]\s*つ選べ")

# 連問の導入。「次の文を読み、47、48の問いに答えよ。」に続く症例文を複数の設問が
# 共有する形式。個々の設問文は「診断はどれか。」のように単独では成立しないため、
# 現状は取り込まない（将来 question_set として扱う余地はある）。
SERIES_HEAD = re.compile(r"次の文を読み[、,]\s*([0-9０-９、,〜～\-]+?)\s*の問いに答えよ")

# pdfplumber がグリフを解決できなかった箇所。本文に "(cid:7674)" の形で残る。
CID_ARTIFACT = re.compile(r"\(cid:\d+\)")

# 設問の通し番号で始まる行（例: "13 Brugada症候群における…"）
Q_START = re.compile(r"^(\d{1,3})[ 　]+(\S.*)$", re.MULTILINE)

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


def pdf_lines(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    lines = []
    for page in pages:
        for line in page.split("\n"):
            if not NOISE_LINE.search(line):
                lines.append(line.rstrip())
    return lines


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
            texts.append("".join(p.strip() for p in parts))

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
        stem = "".join(s.strip() for s in [m.group(2)] + stem_lines[1:])
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

    questions = []
    stats = {"total": 0, "series": 0, "image": 0, "multi": 0, "cid": 0,
             "bad_choices": 0, "no_answer": 0, "ok": 0}

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
            if MULTI_SELECT.search(body):
                stats["multi"] += 1
                continue
            if CID_ARTIFACT.search(body):
                # PDFのグリフを解決できず本文が欠けている。表示できないので落とす。
                stats["cid"] += 1
                continue

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
                "choices": [{"id": k, "text": t} for k, t in zip(CHOICE_KEYS, texts)],
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
    print(f"  選択肢不備で除外: {stats['bad_choices']}")
    print(f"取り込み        : {stats['ok']}")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
