"""模試の採点コマンド (spec フェーズ5).

    python manage.py grade_mock_exam --exam-id 1 [--force]

素点 → 全国順位 → percentile → 偏差値 → 学内順位 → 分野別スコア
（blueprint_code の area 単位）を計算して MockResult を更新し、
MockExam.status を graded にする。模試の解答は AnswerHistory に
context="mock" で複写し、5段階習熟度は付与しない（未演習のまま。
模試後の復習で改めて分類させる, spec フェーズ5）。
"""

import re
import statistics

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from exams.models import MockExam, MockResult
from quiz.models import AnswerHistory

AREA_RE = re.compile(r"^([A-F]-\d+)")


def area_of(question):
    match = AREA_RE.match(question.blueprint_code or "")
    return match.group(1) if match else question.category


class Command(BaseCommand):
    help = "締切後の模試を採点して順位・偏差値・分野別スコアを確定する"

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
        if timezone.now() <= exam.end_at and not options["force"]:
            raise CommandError("終了時刻前です（--force で強制採点）")

        correct_keys = {
            mq.question_id: mq.question
            for mq in exam.mock_questions.select_related("question")
        }
        results = list(
            MockResult.objects.filter(mock_exam=exam, started_at__isnull=False)
            .select_related("user")
            .prefetch_related("answers")
        )
        if not results:
            raise CommandError("受験者がいません")

        # --- 素点 + 分野別スコア + AnswerHistory 複写 ---------------------
        for result in results:
            score = 0
            per_area = {}
            for answer in result.answers.all():
                question = correct_keys.get(answer.question_id)
                if question is None:
                    continue
                is_correct = (
                    answer.selected_choice_key == question.correct_choice_key
                    and answer.selected_choice_key != ""
                )
                score += int(is_correct)
                area = area_of(question)
                per_area.setdefault(area, [0, 0])
                per_area[area][0] += int(is_correct)
                per_area[area][1] += 1

                if not AnswerHistory.objects.filter(
                    user=result.user,
                    question=question,
                    context=AnswerHistory.Context.MOCK,
                    answered_at__gte=exam.start_at,
                ).exists():
                    AnswerHistory.objects.create(
                        user=result.user,
                        question=question,
                        # 習熟度は付与しない＝未演習のまま (spec フェーズ5)
                        mastery_level=AnswerHistory.MasteryLevel.UNSTUDIED,
                        correct=is_correct,
                        response_time_ms=answer.response_time_ms,
                        context=AnswerHistory.Context.MOCK,
                    )

            result.score = score
            result.section_scores = {
                area: round(c / n, 2) for area, (c, n) in sorted(per_area.items()) if n
            }

        # --- 全国順位 / percentile / 偏差値 --------------------------------
        scores = [r.score for r in results]
        mean = statistics.fmean(scores)
        stdev = statistics.pstdev(scores)
        n = len(results)

        ordered = sorted(results, key=lambda r: r.score, reverse=True)
        prev_score, prev_rank = None, 0
        for i, result in enumerate(ordered, start=1):
            result.rank = prev_rank if result.score == prev_score else i
            prev_score, prev_rank = result.score, result.rank
            below = sum(1 for s in scores if s < result.score)
            result.percentile = round(below / n * 100, 1)
            result.deviation_score = (
                round(50 + 10 * (result.score - mean) / stdev, 1) if stdev else 50.0
            )

        # --- 学内順位 --------------------------------------------------------
        by_university = {}
        for result in ordered:
            if result.user.university_id:
                by_university.setdefault(result.user.university_id, []).append(result)
        for members in by_university.values():
            prev_score, prev_rank = None, 0
            for i, result in enumerate(members, start=1):  # ordered は score 降順
                result.university_rank = (
                    prev_rank if result.score == prev_score else i
                )
                prev_score, prev_rank = result.score, result.university_rank

        MockResult.objects.bulk_update(
            ordered,
            ["score", "rank", "percentile", "deviation_score", "section_scores", "university_rank"],
        )
        exam.status = MockExam.Status.GRADED
        exam.save(update_fields=["status"])

        self.stdout.write(
            self.style.SUCCESS(
                f"graded {exam.title}: {n}人, mean={mean:.1f}, sd={stdev:.1f}"
            )
        )
