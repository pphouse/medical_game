"""CBT模試の「予想IRT」用に項目パラメータ（識別力a・困難度b）を較正する。

    python manage.py calibrate_irt

過去の解答履歴（AnswerHistory, 全コンテキスト）から 2PL の周辺最尤推定
（EM法, exams/irt.py）で項目ごとの a/b を求め、ItemParameter に upsert する。
解答数が少ない項目は Question.difficulty から決め打ちした初期値のまま残す。

定期実行（月次程度を想定, spec: CBT模試の予想IRT）。pg_cron から直接
Djangoコマンドは叩けないため、運用に組み込む場合は Vercel Cron 等から
`python manage.py calibrate_irt` を実行する。
"""

from django.core.management.base import BaseCommand

from exams import irt
from exams.models import ItemParameter
from quiz.models import AnswerHistory


class Command(BaseCommand):
    help = "AnswerHistory から IRT 項目パラメータ（a/b）を較正する"

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-responses", type=int, default=20,
            help="この解答数未満の項目は較正せず初期値のままにする",
        )
        parser.add_argument("--iterations", type=int, default=8)

    def handle(self, *args, **options):
        responses = list(
            AnswerHistory.objects.values_list("question_id", "user_id", "correct")
        )
        if not responses:
            self.stdout.write(self.style.WARNING("解答履歴がありません。較正をスキップします。"))
            return

        question_ids = {qid for qid, _, _ in responses}
        existing = {
            p.question_id: {"a": p.a, "b": p.b}
            for p in ItemParameter.objects.filter(question_id__in=question_ids)
        }
        seeded = {}
        from quiz.models import Question

        for question in Question.objects.filter(id__in=question_ids - existing.keys()):
            seeded[question.id] = irt.seed_item_params(question)
        init_params = {**seeded, **existing}

        calibrated = irt.calibrate(
            responses, init_params,
            iterations=options["iterations"], min_responses=options["min_responses"],
        )

        to_update = []
        to_create = []
        already = set(
            ItemParameter.objects.filter(question_id__in=calibrated.keys())
            .values_list("question_id", flat=True)
        )
        for question_id, params in calibrated.items():
            if params["n"] < options["min_responses"]:
                continue
            if question_id in already:
                to_update.append(
                    ItemParameter(question_id=question_id, a=params["a"], b=params["b"], calibrated_n=params["n"])
                )
            else:
                to_create.append(
                    ItemParameter(question_id=question_id, a=params["a"], b=params["b"], calibrated_n=params["n"])
                )

        if to_create:
            ItemParameter.objects.bulk_create(to_create)
        if to_update:
            ItemParameter.objects.bulk_update(to_update, ["a", "b", "calibrated_n"])

        self.stdout.write(
            self.style.SUCCESS(
                f"較正完了: 新規 {len(to_create)}件 / 更新 {len(to_update)}件 "
                f"（解答履歴 {len(responses)}件, 対象問題 {len(question_ids)}問）"
            )
        )
