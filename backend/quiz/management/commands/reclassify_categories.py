"""既存の問題の分野名を正規の分野立てに揃える。

    python manage.py reclassify_categories --dry-run
    python manage.py reclassify_categories

分野名は CBT 出題基準に沿った名前（「呼吸器系」「腎・尿路系」）と、国試
過去問の取り込み時にキーワードで付けた名前（「医師国家試験（分類未確定）」
を含む）が混在していた。quiz.categories の対応表で読み替え、1対1で移せない
ものだけ本文から振り分け直す。
"""

from django.core.management.base import BaseCommand

from quiz.categories import CATEGORY_ORDER, normalize
from quiz.models import Question

BATCH = 500


def question_text_for_classification(q: Question) -> str:
    """分野の推定に使う本文。設問文だけだと手掛かりが足りないことがあるので、
    連問の症例文・トピック・選択肢まで含める。"""
    parts = [q.question_text or "", q.topic or ""]
    if q.question_set_id and q.question_set:
        parts.append(q.question_set.case_stem or "")
    for choice in q.choices or []:
        if isinstance(choice, dict):
            parts.append(str(choice.get("text", "")))
    return "\n".join(parts)


class Command(BaseCommand):
    help = "問題の分野名を正規の分野立て（循環器・呼吸器…公衆衛生・４連問）に揃える。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="変更内容を表示するだけで保存しない。",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        moves: dict[tuple[str, str], int] = {}
        pending: list[Question] = []
        changed = 0

        qs = Question.objects.select_related("question_set").iterator(chunk_size=BATCH)
        for q in qs:
            new = normalize(q.category, question_text_for_classification(q))
            if new == q.category:
                continue
            moves[(q.category, new)] = moves.get((q.category, new), 0) + 1
            q.category = new
            pending.append(q)
            changed += 1
            if not dry_run and len(pending) >= BATCH:
                Question.objects.bulk_update(pending, ["category"])
                pending.clear()

        if not dry_run and pending:
            Question.objects.bulk_update(pending, ["category"])

        for (old, new), n in sorted(moves.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"{n:5d}  {old} -> {new}")

        verb = "変更予定" if dry_run else "変更"
        self.stdout.write(self.style.SUCCESS(f"{changed}問を{verb}しました。"))

        if dry_run:
            return

        remaining = sorted(
            Question.objects.exclude(category__in=CATEGORY_ORDER)
            .values_list("category", flat=True)
            .distinct()
        )
        if remaining:
            self.stdout.write(
                self.style.WARNING(f"正規名でない分野が残っています: {remaining}")
            )
