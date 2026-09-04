"""取り込み済みの解説から、定型文（出典URL・整形の注記）を落とす。

    python manage.py strip_explanation_boilerplate --dry-run
    python manage.py strip_explanation_boilerplate

取り込み時にも落としている（quiz/explanations.strip_boilerplate）ので、
これは既に DB に入っている分の後始末。何度実行しても結果は変わらない。
"""

from django.core.management.base import BaseCommand

from quiz.explanations import strip_boilerplate
from quiz.models import Question

BATCH = 500


class Command(BaseCommand):
    help = "解説から出典URL・整形の注記などの定型文を削除する。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="件数を出すだけで保存しない。"
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        pending, changed = [], 0
        sample = None

        for q in Question.objects.exclude(explanation="").iterator(chunk_size=BATCH):
            cleaned = strip_boilerplate(q.explanation)
            if cleaned == q.explanation:
                continue
            if sample is None:
                sample = (q.id, q.explanation, cleaned)
            q.explanation = cleaned
            pending.append(q)
            changed += 1
            if not dry_run and len(pending) >= BATCH:
                Question.objects.bulk_update(pending, ["explanation"])
                pending.clear()

        if not dry_run and pending:
            Question.objects.bulk_update(pending, ["explanation"])

        if sample:
            qid, before, after = sample
            self.stdout.write(f"例 (Question {qid}):")
            self.stdout.write(f"  変更前: {before!r}")
            self.stdout.write(f"  変更後: {after!r}")

        verb = "削除予定" if dry_run else "削除"
        self.stdout.write(self.style.SUCCESS(f"{changed}問の定型文を{verb}しました。"))
