#!/usr/bin/env python3
"""CBT 出題基準 PDF → data/cbt_blueprint.csv 変換 (spec 3.2).

出典: https://www.cato.or.jp/pdf/cbt_igakuR7.pdf（CATO『医学生共用試験 CBT 出題基準』全98ページ）

    python scripts/extract_blueprint.py --pdf cbt_igakuR7.pdf --out data/cbt_blueprint.csv \
        [--class-table data/class_groups_draft.tsv]

出力 CSV 列: code, section, area, area_title, subsection_title,
             objective_text, depth, class_group, disease_names("|"区切り)

PDF 上のレイアウト（実物で確認済み）:
- 到達目標は「D-5-4)-(2)-③ 〜を説明できる。」のように行頭に完全なコードが付く
- 長い到達目標は2行に折り返され、コードは中央の行に単独で置かれる:
      （前半テキスト）
      C-1-1)-(2)-①
      （後半テキスト）
- 見出しは「D-5　循環器系」「D-7-4)-(6) 膵疾患」のようにコード+タイトル

注意:
- 到達目標の原文 (objective_text) は生成プロンプトの内部用途に限定する。
  生成した CSV を公開リポジトリにコミットしないこと（原典の複製にあたる
  可能性がある）。リポジトリには形式サンプル (data/cbt_blueprint.sample.csv)
  のみを置く。
- Ⅰ群/Ⅱ群疾患一覧は付表（表形式）でレイアウト依存が強いため、--class-table
  で下書き TSV を出すに留め、疾患名→コードの対応付けと class_group 列の記入は
  人手で補正する前提とする（完全自動化しない, spec 3.2-1）。
"""

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("pdfplumber が必要です: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)

CODE = r"[A-F]-\d+(?:-\d+\))?(?:-\(\d+\))?"
# 到達目標（コード+丸数字。テキストは同一行にある場合と、折返しで
# 前後の行に分かれてコード単独行になる場合の両方がある）
OBJECTIVE_RE = re.compile(rf"^({CODE})-([①-⑳])(?:[\s　]+(.+))?$")
# 見出し: 「D-5 循環器系」「D-7-4)-(6) 膵疾患」「C-1-1) 生命の最小単位-細胞」
HEADING_RE = re.compile(rf"^({CODE})[\s　]+(.+)$")
AREA_RE = re.compile(r"^([A-F])-(\d+)$")
SECTION_RE = re.compile(r"^([A-F])[\s　]+(\S.*)$")
PAGE_NUMBER_RE = re.compile(r"^\d+$")

DEPTHS = ("説明できる", "概説できる", "列挙できる", "実施できる", "図示できる")


def detect_depth(text):
    tail = text.rstrip("。 ")
    for depth in DEPTHS:
        if tail.endswith(depth):
            return depth
    return ""


def normalize(line):
    # NFKC は丸数字（①→1）まで潰してしまうため使わない。空白類のみ整える。
    return line.replace(" ", " ").strip()


def extract_objectives(pdf_path):
    rows = []
    seen_codes = set()
    area = area_title = ""
    subsection_title = ""
    fragment = ""  # 折返し到達目標の前半テキスト候補
    pending = None  # (code, circled) コード単独行を読んだ直後

    def emit(code_base, circled, text):
        code = f"{code_base}-{circled}"
        if code in seen_codes:
            return
        seen_codes.add(code)
        rows.append(
            {
                "code": code,
                "section": code_base.split("-")[0],
                "area": "-".join(code_base.split("-")[:2]).split(")")[0].split("(")[0],
                "area_title": area_title,
                "subsection_title": subsection_title,
                "objective_text": text.strip(),
                "depth": detect_depth(text),
                "class_group": "",
                "disease_names": "",
            }
        )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = normalize(raw_line)
                if not line or PAGE_NUMBER_RE.match(line) or line.startswith(("<", "＜")):
                    continue

                m = OBJECTIVE_RE.match(line)
                if m:
                    code_base, circled, inline_text = m.group(1), m.group(2), m.group(3)
                    if inline_text:
                        emit(code_base, circled, inline_text)
                        fragment = ""
                        pending = None
                    else:
                        # コード単独行: 前の行が前半、次の行が後半
                        pending = (code_base, circled)
                    continue

                if pending:
                    code_base, circled = pending
                    emit(code_base, circled, f"{fragment}{line}")
                    pending = None
                    fragment = ""
                    continue

                m = HEADING_RE.match(line)
                if m:
                    code, title = m.group(1), m.group(2).strip()
                    area_match = AREA_RE.match(code)
                    if area_match:
                        area = code
                        area_title = title
                        subsection_title = ""
                    elif area and code.startswith(area):
                        subsection_title = title
                    fragment = ""
                    continue

                m = SECTION_RE.match(line)
                if m and len(m.group(1)) == 1 and area and not line[2:].strip().startswith("-"):
                    # 「D 人体各器官の…」のような大区分見出し
                    fragment = ""
                    continue

                # それ以外の行は折返し到達目標の前半候補として保持
                fragment = line
    return rows


def extract_class_tables(pdf_path, out_path):
    """付表のⅠ群/Ⅱ群疾患一覧をテーブルとして生抽出する（人手補正用の下書き）。"""
    with pdfplumber.open(pdf_path) as pdf, open(out_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "Ⅰ群" not in text and "Ⅱ群" not in text:
                continue
            for table in page.extract_tables():
                f.write(f"# page {i + 1}\n")
                for row in table:
                    f.write("\t".join((cell or "").replace("\n", " ") for cell in row) + "\n")
    print(f"class-group draft -> {out_path} (要・人手補正)")


def main():
    parser = argparse.ArgumentParser(description="CBT出題基準PDFからCSVを生成")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out", default="data/cbt_blueprint.csv")
    parser.add_argument(
        "--class-table",
        help="Ⅰ群/Ⅱ群の表を生抽出するファイルパス（例 data/class_groups_draft.tsv）",
    )
    args = parser.parse_args()

    rows = extract_objectives(args.pdf)
    if not rows:
        print("到達目標を1件も抽出できませんでした。PDFのレイアウトを確認してください。", file=sys.stderr)
        sys.exit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "code",
                "section",
                "area",
                "area_title",
                "subsection_title",
                "objective_text",
                "depth",
                "class_group",
                "disease_names",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} objectives -> {out}")

    if args.class_table:
        extract_class_tables(args.pdf, args.class_table)


if __name__ == "__main__":
    main()
