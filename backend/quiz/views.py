from django.db.models import Avg, Case, Count, F, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import AnswerHistory, Question, ReviewSchedule
from .serializers import (
    CategoryProgressSerializer,
    CategorySerializer,
    HomeSummarySerializer,
    QuestionSerializer,
    ReviewQuestionSerializer,
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

# spec §5-5: correct_rate is no longer recomputed on every answer — the
# per-answer write only increments answer_count, and the rate is refreshed
# every N answers (plus the daily recalc_correct_rates batch).
CORRECT_RATE_RECALC_EVERY = 10


class IsModerator(BasePermission):
    message = "モデレーター権限が必要です。"

    def has_permission(self, request, view):
        profile = request.user
        return bool(getattr(profile, "is_moderator", False))


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


def latest_answers(profile):
    """Rows that are each question's most recent attempt by this user,
    resolved in SQL via a DISTINCT ON subquery (spec §5-7: don't pull every
    question id into Python).

    The DISTINCT ON runs inside the inner subquery, so callers can safely
    add further .filter(...) on mastery_level etc. — a filter applied
    directly to a .distinct("question_id") queryset would be evaluated
    BEFORE the distinct and resurrect older attempts.
    """
    latest_ids = (
        AnswerHistory.objects.filter(user=profile)
        .order_by("question_id", "-answered_at", "-id")
        .distinct("question_id")
        .values("id")
    )
    return AnswerHistory.objects.filter(id__in=latest_ids)


class HomeSummaryView(APIView):
    """Overall progress % plus in-university/national rank shown at the top
    of the home screen.

    spec §5-6: the old implementation annotated & sorted ALL profiles in
    memory on every request; ranks now come from RankingSnapshot (batch),
    and only the caller's own rows are queried live.
    """

    def get(self, request):
        from exams.models import RankingSnapshot

        visible = Question.objects.visible_to(request.user)
        total_questions = visible.count()
        answered_count = (
            AnswerHistory.objects.filter(user=request.user)
            .values("question_id")
            .distinct()
            .count()
        )
        overall_progress_pct = (
            round(answered_count / total_questions * 100, 1) if total_questions else 0.0
        )

        own = AnswerHistory.objects.filter(user=request.user).aggregate(
            acc=Avg(Case(When(correct=True, then=1.0), default=0.0))
        )
        overall_correct_rate = round((own["acc"] or 0) * 100, 1)

        def snapshot_rank(scope, **extra):
            qs = RankingSnapshot.objects.filter(
                scope=scope,
                period="all",
                metric=RankingSnapshot.Metric.SOLVED,
                **extra,
            )
            row = qs.filter(profile=request.user).first()
            return {"rank": row.rank if row else None, "out_of": qs.count()}

        national_rank = snapshot_rank(RankingSnapshot.Scope.NATIONAL)
        university_rank = (
            snapshot_rank(
                RankingSnapshot.Scope.UNIVERSITY,
                university_id=request.user.university_id,
            )
            if request.user.university_id
            else {"rank": None, "out_of": 0}
        )

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


class CategoryListView(APIView):
    def get(self, request):
        rows = (
            Question.objects.visible_to(request.user)
            .values("category")
            .annotate(count=Count("id"))
            .order_by("category")
        )
        return Response(CategorySerializer(rows, many=True).data)


class CategoryProgressView(APIView):
    """Per-category breakdown of the learner's 5-level mastery self-ratings,
    used to render the QB-style category list with segmented progress bars."""

    def get(self, request):
        visible = Question.objects.visible_to(request.user)
        categories = (
            visible.values("category").annotate(total=Count("id")).order_by("category")
        )

        histories = (
            latest_answers(request.user)
            .filter(question__in=visible)
            .values_list("question_id", "question__category", "mastery_level")
        )
        latest_by_question = {
            question_id: (category, mastery_level)
            for question_id, category, mastery_level in histories
        }

        def empty_counts():
            return {level: 0 for level in AnswerHistory.MasteryLevel.values}

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
            counts["unstudied"] += max(total - answered, 0)
            results.append(
                {
                    "category": category,
                    "total": total,
                    "remaining": max(total - answered, 0),
                    "counts": counts,
                }
            )

        return Response(CategoryProgressSerializer(results, many=True).data)


class QuestionPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    # QuestionPicker needs the whole category at once for its mastery-filter
    # chips; categories are far below this bound.
    max_page_size = 500


class QuestionListView(APIView):
    def get(self, request):
        qs = Question.objects.visible_to(request.user)
        category = request.query_params.get("category")
        exam_type = request.query_params.get("exam_type")
        mastery_level = request.query_params.get("mastery_level")
        if category:
            qs = qs.filter(category=category)
        if exam_type:
            qs = qs.filter(exam_type=exam_type)

        latest = latest_answers(request.user)
        if mastery_level:
            if mastery_level == "unstudied":
                # Never answered, or the latest attempt was reset to 未演習.
                qs = qs.exclude(
                    id__in=latest.exclude(mastery_level="unstudied").values("question_id")
                )
            else:
                qs = qs.filter(
                    id__in=latest.filter(mastery_level=mastery_level).values("question_id")
                )

        paginator = QuestionPagination()
        page = paginator.paginate_queryset(
            qs.select_related("question_set").order_by("id"), request
        )

        mastery_by_question = dict(
            latest.filter(question_id__in=[q.id for q in page]).values_list(
                "question_id", "mastery_level"
            )
        )
        serializer = QuestionSerializer(
            page, many=True, context={"mastery_by_question": mastery_by_question}
        )
        return paginator.get_paginated_response(serializer.data)


class ReviewDeckView(APIView):
    """spec: 間違えた問題だけを集めた自分専用の復習デッキ (SM-2ベースで出題タイミングを自動調整)"""

    def get(self, request):
        qs = (
            ReviewSchedule.objects.filter(
                user=request.user,
                next_review_at__lte=timezone.now(),
                question__in=Question.objects.visible_to(request.user),
            )
            .select_related("question", "question__question_set")
            .order_by("next_review_at")
        )
        return Response(ReviewScheduleSerializer(qs, many=True).data)


class ReviewDeckSummaryView(APIView):
    """GET /api/quiz/review-deck/summary/ — 今日/明日/今週の復習件数
    (spec フェーズ6)。アプリ内バッジにも使う。"""

    def get(self, request):
        now = timezone.now()
        local = timezone.localtime(now)
        end_of_today = local.replace(hour=23, minute=59, second=59, microsecond=999999)
        end_of_tomorrow = end_of_today + timezone.timedelta(days=1)
        end_of_week = end_of_today + timezone.timedelta(days=6 - local.weekday())

        qs = ReviewSchedule.objects.filter(
            user=request.user,
            question__in=Question.objects.visible_to(request.user),
        )
        due_now = qs.filter(next_review_at__lte=now).count()
        return Response(
            {
                "due_now": due_now,
                "today": qs.filter(next_review_at__lte=end_of_today).count(),
                "tomorrow": qs.filter(
                    next_review_at__gt=end_of_today, next_review_at__lte=end_of_tomorrow
                ).count(),
                "this_week": qs.filter(next_review_at__lte=end_of_week).count(),
            }
        )


class SubmitAnswerView(APIView):
    """Step 1: grade the selected choice, record the attempt, and
    auto-classify mastery from correctness (correct -> ○, incorrect -> ✕).

    ◎ and △ are never assigned automatically; the learner can only reach
    them by explicitly tapping one via SubmitMasteryView. A separate
    「分からない」 action also goes through SubmitMasteryView and maps to
    unstudied (treats the question as not yet learned, regardless of
    whether the guess happened to be correct).
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "submit-answer"

    def post(self, request):
        payload = SubmitAnswerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        question = get_object_or_404(
            Question.objects.visible_to(request.user), pk=data["question_id"]
        )
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
            context=data["context"],
        )

        # spec §5-5: no per-answer full recomputation. Increment the
        # denominator and refresh correct_rate only every Nth answer
        # (recalc_correct_rates covers the rest daily).
        Question.objects.filter(pk=question.pk).update(
            answer_count=F("answer_count") + 1
        )
        question.refresh_from_db(fields=["answer_count", "correct_rate"])
        if question.answer_count % CORRECT_RATE_RECALC_EVERY == 0:
            agg = question.answer_histories.aggregate(
                rate=Avg(Case(When(correct=True, then=1.0), default=0.0))
            )
            question.correct_rate = round((agg["rate"] or 0) * 100, 1)
            question.save(update_fields=["correct_rate"])

        review_schedule = update_review_schedule(request.user, question, auto_mastery)

        return Response(
            {
                "answer_history_id": answer_history.id,
                "correct": is_correct,
                "correct_choice_key": question.correct_choice_key,
                "explanation": question.explanation,
                "correct_rate": question.public_correct_rate,
                "mastery_level": auto_mastery,
                "next_review_at": review_schedule.next_review_at if review_schedule else None,
            }
        )


class SubmitMasteryView(APIView):
    """Override the auto-assigned mastery: only reachable by the learner
    explicitly tapping ◎ / △ / 分からない. Re-runs the SM-2 scheduling with
    the new self-assessment."""

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


class ReviewQueueView(APIView):
    """審査待ち問題の一覧（モデレーター専用）。

    医学的正確性の最終判断は人間が行う。LLM 生成問題を無審査で published に
    してはならない (spec 2-4)。承認は ReviewActionView から。
    """

    permission_classes = [IsModerator]

    def get(self, request):
        status_filter = request.query_params.get("status", Question.Status.PENDING)
        qs = (
            Question.objects.filter(status=status_filter)
            .select_related("question_set")
            .order_by("created_at")
        )
        paginator = QuestionPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            ReviewQuestionSerializer(page, many=True).data
        )


class ReviewActionView(APIView):
    """承認/却下。reviewed_by / reviewed_at を記録する (spec 2-4)."""

    permission_classes = [IsModerator]

    def post(self, request, question_id, action):
        if action not in ("approve", "reject"):
            raise exceptions.ValidationError("action は approve / reject のみ")
        question = get_object_or_404(Question, pk=question_id)
        question.status = (
            Question.Status.PUBLISHED if action == "approve" else Question.Status.REJECTED
        )
        question.reviewed_by = request.user
        question.reviewed_at = timezone.now()
        question.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        # タイプQはセット単位で公開状態を揃える
        if question.question_set_id:
            siblings = question.question_set.questions.exclude(pk=question.pk)
            if action == "approve" and not siblings.exclude(
                status=Question.Status.PUBLISHED
            ).exists():
                question.question_set.status = Question.Status.PUBLISHED
                question.question_set.save(update_fields=["status"])
            if action == "reject":
                question.question_set.status = Question.Status.REJECTED
                question.question_set.save(update_fields=["status"])

        return Response(ReviewQuestionSerializer(question).data)
