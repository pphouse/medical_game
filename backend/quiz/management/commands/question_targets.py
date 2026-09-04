"""科目ごとの問題数の過不足を出す。

    python manage.py question_targets                 # CBT・国試の両方
    python manage.py question_targets --exam-type CBT
    python manage.py question_targets --total 2000    # 目標総数を指定
    python manage.py question_targets --json          # 機械可読

「最低どの科目も15問」＋「残りは本番の出題構成比で比例配分」を目標とし
（quiz/blueprint_weights.py）、公開済み（status=published）の実数と突き
合わせて不足数を出す。何をどれだけ作れば偏りが解消するかを、勘ではなく
数字で決めるための土台。

目標総数（--total）を省略した場合は「現在の公開済み総数」と「最低数の
合計」の大きい方を使う。つまり総数を増やさずに配分だけを見るときは
そのまま実行すればよい。
"""

import json

from django.core.management.base import BaseCommand
from django.db.models import Count

from quiz.blueprint_weights import (
    MIN_QUESTIONS_PER_CATEGORY,
    share_of,
    target_counts,
    weights_for,
)
from quiz.models import Question


def report_for(exam_type, total=None, minimum=MIN_QUESTIONS_PER_CATEGORY):
    """[{category, current, target, shortfall, share}] を目標順で返す。"""
    weights = weights_for(exam_type)
    current = {
        row["category"]: row["n"]
        for row in Question.objects.published()
        .filter(exam_type=exam_type)
        .values("category")
        .annotate(n=Count("id"))
    }
    if total is None:
        total = max(sum(current.values()), minimum * len(weights))
    targets = target_counts(exam_type, total, minimum=minimum)
    rows = []
    for category, target in targets.items():
        have = current.get(category, 0)
        rows.append(
            {
                "category": category,
                "current": have,
                "target": target,
                "shortfall": max(0, target - have),
                "share": round(share_of(exam_type, category) * 100, 1),
            }
        )
    rows.sort(key=lambda r: (-r["shortfall"], -r["target"], r["category"]))
    return rows


class Command(BaseCommand):
    help = "科目ごとの目標問題数（最低15問＋出題構成比での比例配分）と不足数を表示する。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--exam-type",
            choices=[t for t, _ in Question.ExamType.choices],
            help="省略時は CBT・医師国家試験の両方。",
        )
        parser.add_argument(
            "--total", type=int, default=None, help="目標とする総問題数。"
        )
        parser.add_argument(
            "--minimum",
            type=int,
            default=MIN_QUESTIONS_PER_CATEGORY,
            help=f"どの科目にも確保する最低問題数（既定 {MIN_QUESTIONS_PER_CATEGORY}）。",
        )
        parser.add_argument("--json", action="store_true", help="JSON で出力する。")

    def handle(self, *args, **options):
        exam_types = (
            [options["exam_type"]]
            if options["exam_type"]
            else [t for t, _ in Question.ExamType.choices]
        )
        payload = {}
        for exam_type in exam_types:
            rows = report_for(exam_type, options["total"], options["minimum"])
            payload[exam_type] = rows
            if options["json"]:
                continue
            self._print_table(exam_type, rows)

        if options["json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

    def _print_table(self, exam_type, rows):
        label = dict(Question.ExamType.choices)[exam_type]
        shortfall = sum(r["shortfall"] for r in rows)
        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"== {label}  現在 {sum(r['current'] for r in rows)}問 "
                f"/ 目標 {sum(r['target'] for r in rows)}問  不足 {shortfall}問"
            )
        )
        self.stdout.write(f"{'科目':<24}{'現在':>6}{'目標':>6}{'不足':>6}{'構成比':>8}")
        for row in rows:
            line = (
                f"{row['category']:<24}{row['current']:>6}{row['target']:>6}"
                f"{row['shortfall']:>6}{row['share']:>7.1f}%"
            )
            if row["current"] < MIN_QUESTIONS_PER_CATEGORY:
                # 最低数すら満たしていない科目は演習が成立しないので目立たせる。
                self.stdout.write(self.style.ERROR(line))
            elif row["shortfall"]:
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(line)
