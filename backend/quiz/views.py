from django.db.models import Avg, Case, Count, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import AnswerHistory, Question, ReviewSchedule
from .serializers import (
    CategoryProgressSerializer,
    CategorySerializer,
    HomeSummarySerializer,
    QuestionSerializer,
    ReviewScheduleSerializer,
    SubmitAnswerSerializer,
    SubmitMasterySerializer,
)
from .sm2 import MASTERY_TO_QUALITY, schedule_next_review

# Mastery levels that keep a question in the personal review deck. ◎/○
# ("solid") don't need repeated review unless the learner manually flags
# them via △ or 分からない.
NEEDS_REVIEW_LEVELS = {
    AnswerHistory.MasteryLevel.TRIANGLE,
    AnswerHistory.MasteryLevel.CROSS,
    AnswerHistory.MasteryLevel.UNSTUDIED,
}


def update_review_schedule(user, question, mastery_level):
    existing = ReviewSchedule.objects.filter(user=user, question=question).first()
    if existing is None and mastery_level not in NEEDS_REVIEW_LEVELS:
        return None

    quality = MASTERY_TO_QUALITY[mastery_level]
    interval_days = existing.interval_days if existing else 1.0
    ease_factor = existing.ease_factor if existing else 2.5
    next_interval, next_ease_factor, next_review_at = schedule_next_review(
        interval_days=interval_days, ease_factor=ease_factor, quality=quality
    )

    if existing:
        existing.interval_days = next_interval
        existing.ease_factor = next_ease_factor
        existing.next_review_at = next_review_at
        existing.save()
        return existing

    return ReviewSchedule.objects.create(
        user=user,
        question=question,
        interval_days=next_interval,
        ease_factor=next_ease_factor,
        next_review_at=next_review_at,
    )


class HomeSummaryView(APIView):
    """Overall progress % plus live-computed in-university/national rank by
    accuracy, shown at the top of the home screen.

    Note: this is a lightweight live computation for the home-screen widget,
    distinct from the spec's `MonthlyRanking` (a batch-computed, monthly,
    questions_solved>=1000-gated leaderboard planned for phase 2).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        total_questions = Question.objects.count()
        answered_question_ids = set(
            AnswerHistory.objects.filter(user=request.user).values_list(
                "question_id", flat=True
            )
        )
        overall_progress_pct = (
            round(len(answered_question_ids) / total_questions * 100, 1)
            if total_questions
            else 0.0
        )

        ranked_users = list(
            User.objects.annotate(
                answered=Count("answer_histories"),
                acc=Avg(Case(When(answer_histories__correct=True, then=1), default=0)),
            )
            .filter(answered__gt=0)
            .order_by("-acc")
        )

        national_rank = self._rank_of(request.user, ranked_users)
        university_users = [u for u in ranked_users if u.university_id == request.user.university_id]
        university_rank = (
            self._rank_of(request.user, university_users)
            if request.user.university_id
            else {"rank": None, "out_of": 0}
        )

        own_stats = next((u for u in ranked_users if u.id == request.user.id), None)
        overall_correct_rate = round((own_stats.acc or 0) * 100, 1) if own_stats else 0.0

        return Response(
            HomeSummarySerializer(
                {
                    "overall_progress_pct": overall_progress_pct,
                    "overall_correct_rate": overall_correct_rate,
                    "university_rank": university_rank,
                    "national_rank": national_rank,
                }
            ).data
        )

    @staticmethod
    def _rank_of(user, ranked_list):
        for i, u in enumerate(ranked_list):
            if u.id == user.id:
                return {"rank": i + 1, "out_of": len(ranked_list)}
        return {"rank": None, "out_of": len(ranked_list)}


class CategoryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = (
            Question.objects.values("category")
            .annotate(count=Count("id"))
            .order_by("category")
        )
        return Response(CategorySerializer(rows, many=True).data)


class CategoryProgressView(APIView):
    """Per-category breakdown of the learner's 5-level mastery self-ratings,
    used to render the QB-style category list with segmented progress bars
    on the home screen."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        categories = (
            Question.objects.values("category")
            .annotate(total=Count("id"))
            .order_by("category")
        )

        histories = (
            AnswerHistory.objects.filter(user=request.user)
            .order_by("question_id", "-answered_at")
            .values_list("question_id", "question__category", "mastery_level")
        )
        # Keep only the most recent attempt per question (first row per
        # question_id, since histories are ordered by -answered_at).
        latest_by_question = {}
        for question_id, category, mastery_level in histories:
            if question_id not in latest_by_question:
                latest_by_question[question_id] = (category, mastery_level)

        empty_counts = lambda: {level: 0 for level in AnswerHistory.MasteryLevel.values}
        counts_by_category = {}
        answered_by_category = {}
        for category, mastery_level in latest_by_question.values():
            counts_by_category.setdefault(category, empty_counts())[mastery_level] += 1
            answered_by_category[category] = answered_by_category.get(category, 0) + 1

        results = []
        for row in categories:
            category, total = row["category"], row["total"]
            counts = counts_by_category.get(category, empty_counts())
            answered = answered_by_category.get(category, 0)
            counts["unstudied"] += total - answered
            results.append(
                {
                    "category": category,
                    "total": total,
                    "remaining": total - answered,
                    "counts": counts,
                }
            )

        return Response(CategoryProgressSerializer(results, many=True).data)


class QuestionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Question.objects.all()
        category = request.query_params.get("category")
        exam_type = request.query_params.get("exam_type")
        mastery_level = request.query_params.get("mastery_level")
        if category:
            qs = qs.filter(category=category)
        if exam_type:
            qs = qs.filter(exam_type=exam_type)

        question_ids = list(qs.values_list("id", flat=True))
        histories = (
            AnswerHistory.objects.filter(user=request.user, question_id__in=question_ids)
            .order_by("question_id", "-answered_at")
            .values_list("question_id", "mastery_level")
        )
        mastery_by_question = {}
        for question_id, level in histories:
            if question_id not in mastery_by_question:
                mastery_by_question[question_id] = level

        if mastery_level:
            if mastery_level == "unstudied":
                qs = qs.exclude(id__in=[qid for qid, lvl in mastery_by_question.items() if lvl != "unstudied"])
            else:
                matching_ids = [qid for qid, lvl in mastery_by_question.items() if lvl == mastery_level]
                qs = qs.filter(id__in=matching_ids)

        serializer = QuestionSerializer(
            qs.order_by("id"),
            many=True,
            context={"mastery_by_question": mastery_by_question},
        )
        return Response(serializer.data)


class ReviewDeckView(APIView):
    """spec: 間違えた問題だけを集めた自分専用の復習デッキ (SM-2ベースで出題タイミングを自動調整)"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            ReviewSchedule.objects.filter(
                user=request.user, next_review_at__lte=timezone.now()
            )
            .select_related("question")
            .order_by("next_review_at")
        )
        return Response(ReviewScheduleSerializer(qs, many=True).data)


class SubmitAnswerView(APIView):
    """Step 1: grade the selected choice, record the attempt, and
    auto-classify mastery from correctness (correct -> ○, incorrect -> ✕).

    ◎ and △ are never assigned automatically; the learner can only reach
    them by explicitly tapping one via SubmitMasteryView. A separate
    「分からない」 action also goes through SubmitMasteryView and maps to
    unstudied (treats the question as not yet learned, regardless of
    whether the guess happened to be correct).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = SubmitAnswerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        question = get_object_or_404(Question, pk=data["question_id"])
        is_correct = data["selected_choice_key"] == question.correct_choice_key
        auto_mastery = (
            AnswerHistory.MasteryLevel.CIRCLE
            if is_correct
            else AnswerHistory.MasteryLevel.CROSS
        )

        answer_history = AnswerHistory.objects.create(
            user=request.user,
            question=question,
            mastery_level=auto_mastery,
            correct=is_correct,
            response_time_ms=data["response_time_ms"],
        )

        # correct_rate is described in the spec as batch-updated; recomputed
        # inline here (no scheduler in this demo) so the UI reflects reality.
        agg = question.answer_histories.aggregate(
            correct_rate=Avg(Case(When(correct=True, then=1), default=0))
        )
        question.correct_rate = round((agg["correct_rate"] or 0) * 100, 1)
        question.save(update_fields=["correct_rate"])

        review_schedule = update_review_schedule(request.user, question, auto_mastery)

        return Response(
            {
                "answer_history_id": answer_history.id,
                "correct": is_correct,
                "correct_choice_key": question.correct_choice_key,
                "explanation": question.explanation,
                "correct_rate": question.correct_rate,
                "mastery_level": auto_mastery,
                "next_review_at": review_schedule.next_review_at if review_schedule else None,
            }
        )


class SubmitMasteryView(APIView):
    """Override the auto-assigned mastery: only reachable by the learner
    explicitly tapping ◎ / △ / 分からない. Re-runs the SM-2 scheduling with
    the new self-assessment."""

    permission_classes = [IsAuthenticated]

    def post(self, request, answer_history_id):
        payload = SubmitMasterySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        mastery_level = payload.validated_data["mastery_level"]

        answer_history = get_object_or_404(
            AnswerHistory, pk=answer_history_id, user=request.user
        )
        answer_history.mastery_level = mastery_level
        answer_history.save(update_fields=["mastery_level"])

        review_schedule = update_review_schedule(
            request.user, answer_history.question, mastery_level
        )

        return Response(
            {
                "next_review_at": review_schedule.next_review_at if review_schedule else None,
            }
        )
