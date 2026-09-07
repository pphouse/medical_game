"""選択肢ごとの解説がどれだけ入っているかを出す。

    python manage.py choice_explanation_coverage
    python manage.py choice_explanation_coverage --missing   # 不足の問題IDも出す

「全ての問題に選択肢ごとの解説を入れる」ための進捗表。表示側
（Question.choice_explanations）は用意できているので、あとは中身が要る。
取り込みバッチに distractor_rationale があるものは自動で入るが、無いバッチ
（国試の過去問など）は解説を書き起こさないと埋まらない。
"""

from django.core.management.base import BaseCommand

from quiz.models import Question


def coverage_rows(exam_type=None):
    """[{exam_type, category, total, full, partial, none}] を返す。

    full   … 正解以外の全選択肢に解説がある
    partial… 一部の選択肢にだけある
    none   … 1つも無い
    """
    qs = Question.objects.all()
    if exam_type:
        qs = qs.filter(exam_type=exam_type)

    buckets = {}
    for q in qs.only(
        "id", "exam_type", "category", "choices", "correct_choice_key", "choice_explanations"
    ).iterator(chunk_size=500):
        keys = {c.get("key") for c in (q.choices or []) if isinstance(c, dict)}
        wanted = keys - {q.correct_choice_key}
        have = {k for k, v in (q.choice_explanations or {}).items() if str(v).strip()}
        row = buckets.setdefault(
            (q.exam_type, q.category),
            {"exam_type": q.exam_type, "category": q.category,
             "total": 0, "full": 0, "partial": 0, "none": 0},
        )
        row["total"] += 1
        if wanted and wanted <= have:
            row["full"] += 1
        elif have:
            row["partial"] += 1
        else:
            row["none"] += 1
    return sorted(buckets.values(), key=lambda r: (r["exam_type"], -r["none"], r["category"]))


class Command(BaseCommand):
    help = "選択肢ごとの解説の充足率を分野ごとに表示する。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--exam-type", choices=[t for t, _ in Question.ExamType.choices]
        )
        parser.add_argument(
            "--missing",
            action="store_true",
            help="解説が1つも無い問題のIDを列挙する。",
        )

    def handle(self, *args, **options):
        rows = coverage_rows(options["exam_type"])
        total = sum(r["total"] for r in rows)
        full = sum(r["full"] for r in rows)
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"選択肢ごとの解説: {full}/{total}問 "
                f"({(full / total * 100) if total else 0:.1f}%) が全誤答ぶんそろっている"
            )
        )
        self.stdout.write(f"{'試験':<9}{'科目':<24}{'全部':>6}{'一部':>6}{'なし':>6}{'計':>6}")
        for r in rows:
            line = (
                f"{r['exam_type']:<9}{r['category']:<24}"
                f"{r['full']:>6}{r['partial']:>6}{r['none']:>6}{r['total']:>6}"
            )
            self.stdout.write(self.style.ERROR(line) if r["none"] else line)

        if options["missing"]:
            ids = list(
                Question.objects.filter(choice_explanations={})
                .values_list("id", flat=True)
                .order_by("id")
            )
            self.stdout.write("")
            self.stdout.write(f"解説が1つも無い問題 {len(ids)}件: {ids[:200]}")
            if len(ids) > 200:
                self.stdout.write(f"…ほか {len(ids) - 200}件")
