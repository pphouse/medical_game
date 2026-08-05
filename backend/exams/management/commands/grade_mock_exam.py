"""模試の採点コマンド（週次/月次/大型模試向け。CBT模試(生涯1回)は対象外）。

    python manage.py grade_mock_exam --exam-id 1 [--force]

素点 → 全国順位 → percentile → 偏差値 → 学内順位 → 分野別スコア
（blueprint_code の area 単位）を計算して MockResult を更新し、
MockExam.status を graded にする。模試の解答は AnswerHistory に
context="mock" で複写し、5段階習熟度は付与しない（未演習のまま。
模試後の復習で改めて分類させる）。

kind による追加処理:
  weekly/monthly: 順位バケット＋解答速度ボーナスで対戦と合算のランクポイントを増減
  large         : 分野別の偏差値 + 得点分布ヒストグラムを算出（ポイントは増減しない）

CBT模試（生涯1回, kind=cbt_once）は受験者ごとに受験終了タイミングが違う
（いつでも受験可・生涯1回）ため、このバッチコマンドではなく提出時に
即時採点する（exams/views.py ExamSubmitView, exams/grading.py 参照）。
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from exams.grading import (
    apply_exam_points,
    apply_large_section_deviations,
    apply_rank_stats,
    apply_score_distribution,
    area_of,  # re-exported: create_scheduled_exam.py imports area_of from here
    grade_single_result,
)
from exams.models import MockExam, MockResult

__all__ = ["Command", "area_of"]


class Command(BaseCommand):
    help = "締切後の模試（週次/月次/大型）を採点して順位・偏差値・分野別スコア・ポイントを確定する"

    def add_arguments(self, parser):
        parser.add_argument("--exam-id", type=int, required=True)
        parser.add_argument(
            "--force",
            action="store_true",
            help="終了時刻前でも採点する（テスト・再採点用）",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        exam = MockExam.objects.filter(pk=options["exam_id"]).first()
        if exam is None:
            raise CommandError("MockExam が見つかりません")
        if exam.kind == MockExam.Kind.CBT_ONCE:
            raise CommandError(
                "CBT模試（生涯1回）は提出時に個別採点されます。このコマンドの対象外です。"
            )
        if timezone.now() <= exam.end_at and not options["force"]:
            raise CommandError("終了時刻前です（--force で強制採点）")

        correct_questions = {
            mq.question_id: mq.question
            for mq in exam.mock_questions.select_related("question")
        }
        results = list(
            MockResult.objects.filter(mock_exam=exam, started_at__isnull=False)
            .select_related("user", "mock_exam")
            .prefetch_related("answers")
        )
        if not results:
            raise CommandError("受験者がいません")

        for result in results:
            grade_single_result(result, correct_questions)

        ordered = apply_rank_stats(results)

        update_fields = [
            "score", "rank", "percentile", "deviation_score", "section_scores", "university_rank",
        ]
        if exam.kind in (MockExam.Kind.WEEKLY, MockExam.Kind.MONTHLY):
            apply_exam_points(ordered)
            update_fields.append("points_delta")
        elif exam.kind == MockExam.Kind.LARGE:
            apply_large_section_deviations(ordered)
            apply_score_distribution(ordered)
            update_fields += ["section_deviation_scores", "score_distribution"]

        MockResult.objects.bulk_update(ordered, update_fields)
        exam.status = MockExam.Status.GRADED
        exam.save(update_fields=["status"])

        n = len(ordered)
        mean_score = sum(r.score for r in ordered) / n
        self.stdout.write(
            self.style.SUCCESS(
                f"graded {exam.title} ({exam.kind}): {n}人, mean={mean_score:.1f}"
            )
        )
