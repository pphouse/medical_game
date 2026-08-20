#!/usr/bin/env python3
"""生成バッチの検証（必須ゲート, spec 2-3）。

    python scripts/validate_questions.py --file data/generated/xxx.json [--check-db] [--report report.json]

チェック内容:
- JSON Schema 検証（schemas/question_batch.schema.json）
- 構造: 選択肢5個 / correct_choice_id の存在 / 選択肢テキスト重複なし
- バイアス: 「正解が最長」の割合がバッチ内で40%超なら警告
- 正解キー分布: A〜E が各15〜25%の範囲外なら警告（再生成を促す）
- 文字数: 設問 40〜600字、解説 80〜600字（source_note がある逐語引用は設問文を 6〜1500字とし、抽出失敗の検出のみを目的とする）
- 禁止語: 「すべて選べ」「〜でないものはどれか」「令和N年の統計」等（逐語引用には非適用）
- 重複: 正規化ハッシュ（バッチ内=fail）+ --check-db で既存 DB と
  pg_trgm 類似度 0.75 以上を疑わしいとして警告（人手確認へ）

**fail が1件でもあれば exit 1 = インポート中断。**
"""

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "question_batch.schema.json"

QUESTION_TEXT_RANGE = (40, 600)
# 逐語引用（source_note あり）の設問文の許容範囲。作問の良し悪しを測る 40〜600字
# とは目的が違い、「抽出に失敗していないか」だけを見る。
#
# 過去問の実測（第116〜119回）では 7字（「妄想はどれか。」第118回B-20）から
# 770字（所見を網羅した臨床問題。第117回A-20）まで実在した。したがってこの幅は
# 正常値であり、弾いてはいけない。設問文の断片しか残らない抽出失敗と、複数問が
# 連結してしまう抽出失敗を拾える範囲として余裕を持たせる。
VERBATIM_QUESTION_RANGE = (6, 1500)
EXPLANATION_RANGE = (80, 600)
KEY_DISTRIBUTION_RANGE = (0.15, 0.25)
LONGEST_CORRECT_WARN_RATIO = 0.40
TRIGRAM_THRESHOLD = 0.75

BANNED_PATTERNS = [
    r"すべて選べ",
    r"全て選べ",
    r"以下のうち誤っている",
    r"誤っているものはどれか",
    r"誤っているのはどれか",
    r"正しくないものはどれか",
    r"でないものはどれか",
    r"(令和|平成)\s?\d+\s?年.{0,10}(統計|調査)",
    r"国民健康・栄養調査",
    r"人口動態統計",
]


def normalize_text(text):
    """重複判定用の正規化: 記号除去・年齢/性別のマスク・空白圧縮 (spec 2-3)."""
    text = re.sub(r"\d+\s*(歳|か月|ヶ月|カ月)", "N歳", text)
    text = re.sub(r"(男性|女性|男児|女児|男|女)", "SEX", text)
    text = re.sub(r"[０-９0-9]+", "N", text)
    text = re.sub(r"[、。・,.\s()（）「」『』〈〉<>％%]", "", text)
    return text


def iter_items(batch):
    """(kind, item) で全設問を列挙。question_set の step も1問として数える。"""
    for q in batch.get("questions", []):
        yield "question", q
    for s in batch.get("question_sets", []):
        for step in s.get("steps", []):
            step = dict(step)
            step.setdefault("id", f"{s.get('id', 'set')}-step{step.get('set_order')}")
            yield "set_step", step


class Report:
    def __init__(self):
        self.failures = []
        self.warnings = []
        self.checked = 0

    def fail(self, item_id, check, message):
        self.failures.append({"id": item_id, "check": check, "message": message})

    def warn(self, item_id, check, message):
        self.warnings.append({"id": item_id, "check": check, "message": message})

    def to_dict(self):
        return {
            "checked": self.checked,
            "pass": not self.failures,
            "failures": self.failures,
            "warnings": self.warnings,
        }


def validate_schema(batch, report):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for error in validator.iter_errors(batch):
        path = "/".join(str(p) for p in error.absolute_path)
        report.fail(path or "$", "schema", error.message[:300])


def validate_items(batch, report):
    key_counter = collections.Counter()
    longest_correct = 0
    total = 0
    seen_hashes = {}

    for _, item in iter_items(batch):
        item_id = item.get("id", "?")
        report.checked += 1
        total += 1

        choices = item.get("choices", [])
        choice_ids = [c.get("id") for c in choices]
        texts = [c.get("text", "") for c in choices]
        correct = item.get("correct_choice_id")

        if len(choices) != 5:
            report.fail(item_id, "choices", f"選択肢が{len(choices)}個（5個必要）")
        if correct not in choice_ids:
            report.fail(item_id, "correct_choice", f"correct_choice_id={correct} が選択肢に存在しない")
        if len(set(texts)) != len(texts):
            report.fail(item_id, "duplicate_choice_text", "選択肢テキストが重複")
        if len(choice_ids) != len(set(choice_ids)):
            report.fail(item_id, "duplicate_choice_id", "選択肢IDが重複")

        if correct in choice_ids and texts:
            correct_text = texts[choice_ids.index(correct)]
            if len(correct_text) >= max(len(t) for t in texts):
                longest_correct += 1
        key_counter[correct] += 1

        # source_note を持つ設問は外部の公表物からの逐語引用（例: 厚労省が
        # 公表する医師国家試験の過去問）。原文を書き換えると出典を偽ることに
        # なるため、作問スタイルを整えるための検査は適用しない。構造の検査
        # （選択肢5個・正解キー・重複）は引き続き全設問に適用する。
        verbatim = bool(item.get("source_note"))

        qlen = len(item.get("question_text", ""))
        lo, hi = VERBATIM_QUESTION_RANGE if verbatim else QUESTION_TEXT_RANGE
        if not lo <= qlen <= hi:
            report.fail(item_id, "question_length", f"設問文 {qlen}字（{lo}〜{hi}字）")
        elen = len(item.get("explanation", ""))
        if not EXPLANATION_RANGE[0] <= elen <= EXPLANATION_RANGE[1]:
            report.fail(item_id, "explanation_length", f"解説 {elen}字（80〜600字）")

        if not verbatim:
            haystack = item.get("question_text", "") + "".join(texts)
            for pattern in BANNED_PATTERNS:
                if re.search(pattern, haystack):
                    report.fail(item_id, "banned_phrase", f"禁止パターン: {pattern}")

        digest = hashlib.md5(
            normalize_text(item.get("question_text", "")).encode()
        ).hexdigest()
        if digest in seen_hashes:
            report.fail(item_id, "duplicate_in_batch", f"{seen_hashes[digest]} と実質同一の設問文")
        seen_hashes[digest] = item_id

    if total:
        ratio = longest_correct / total
        if ratio > LONGEST_CORRECT_WARN_RATIO:
            report.warn(
                "$batch",
                "longest_correct_bias",
                f"正解が最長選択肢のケースが{ratio:.0%}（40%超）— 典型バイアス。再生成を推奨",
            )
        lo, hi = KEY_DISTRIBUTION_RANGE
        for key in "ABCDE":
            share = key_counter.get(key, 0) / total
            if not lo <= share <= hi:
                report.warn(
                    "$batch",
                    "key_distribution",
                    f"正解キー{key}が{share:.0%}（15〜25%の範囲外）— 偏りあり。再生成を推奨",
                )


def validate_against_db(batch, report):
    """既存 DB との近似重複を pg_trgm 類似度で検出（0.75以上 → 人手確認）。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _django import setup_django

    setup_django()
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        if cursor.fetchone() is None:
            report.warn("$batch", "db_similarity", "pg_trgm 拡張が無効のため DB 類似チェックをスキップ")
            return
        for _, item in iter_items(batch):
            cursor.execute(
                """
                SELECT id, similarity(question_text, %s) AS sim
                FROM quiz_question
                WHERE similarity(question_text, %s) >= %s
                ORDER BY sim DESC LIMIT 3
                """,
                [item.get("question_text", ""), item.get("question_text", ""), TRIGRAM_THRESHOLD],
            )
            for row in cursor.fetchall():
                report.warn(
                    item.get("id", "?"),
                    "db_similarity",
                    f"既存問題 id={row[0]} と類似度 {row[1]:.2f}（>=0.75）— 人手確認へ",
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--check-db", action="store_true", help="既存DBとのpg_trgm類似チェックも行う")
    parser.add_argument("--report", default=None, help="report.json の出力先（既定: <file>のreport.json）")
    args = parser.parse_args()

    path = Path(args.file)
    batch = json.loads(path.read_text(encoding="utf-8"))

    report = Report()
    validate_schema(batch, report)
    validate_items(batch, report)
    if args.check_db:
        validate_against_db(batch, report)

    report_path = Path(args.report) if args.report else path.with_suffix(".report.json")
    report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"checked: {report.checked} items")
    for w in report.warnings:
        print(f"  warn [{w['check']}] {w['id']}: {w['message']}")
    for f in report.failures:
        print(f"  FAIL [{f['check']}] {f['id']}: {f['message']}")
    print(f"report -> {report_path}")

    if report.failures:
        print(f"\nNG: {len(report.failures)}件のfail。インポートを中断してください。")
        sys.exit(1)
    print("\nOK: all checks passed（warningは人手確認のこと）")


if __name__ == "__main__":
    main()
