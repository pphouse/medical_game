from django.db.models import Avg, Case, Count, F, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from config.permissions import IsModerator

from .categories import category_sort_key
from .models import AnswerHistory, Question, QuestionReport, ReviewSchedule
from .serializers import (
    CategoryProgressSerializer,
    CategorySerializer,
    HomeSummarySerializer,
    QuestionSerializer,
    ReviewQuestionSerializer,
    ReviewScheduleSerializer,
    SubmitAnswerSerializer,
    SubmitMasterySerializer,
    UserQuestionSerializer,
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
            # ランキング画面（RankingView）と同じく同学年の中での順位にする
            # ので、RankingSnapshot.rank（学年をまたいだ全体順位）はそのまま
            # 使わず、grade_ranked_rows で学年ごとに振り直す。
            if request.user.grade is None:
                return {"rank": None, "out_of": 0}
            from exams.ranking_utils import grade_ranked_rows

            qs = RankingSnapshot.objects.filter(
                scope=scope,
                period="all",
                metric=RankingSnapshot.Metric.SOLVED,
                **extra,
            )
            ranked_rows = grade_ranked_rows(qs, request.user.grade)
            match = next(
                (r for r in ranked_rows if r[1].profile_id == request.user.id), None
            )
            return {"rank": match[0] if match else None, "out_of": len(ranked_rows)}

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
                    "answered_count": answered_count,
                    "total_questions": total_questions,
                    "university_rank": university_rank,
                    "national_rank": national_rank,
                }
            ).data
        )


class CategoryListView(APIView):
    def get(self, request):
        # 科目立ては CBT と国試で違うので、並び順もその試験のものを使う。
        exam_type = request.query_params.get("exam_type") or "CBT"
        visible = Question.objects.visible_to(request.user)
        if request.query_params.get("exam_type"):
            visible = visible.filter(exam_type=exam_type)
        rows = list(visible.values("category").annotate(count=Count("id")))
        rows.sort(key=lambda r: category_sort_key(r["category"], exam_type))
        return Response(CategorySerializer(rows, many=True).data)


class CategoryProgressView(APIView):
    """Per-category breakdown of the learner's 5-level mastery self-ratings,
    used to render the QB-style category list with segmented progress bars.

    `?exam_type=CBT` / `?exam_type=KOKUSHI` narrows the list to one exam.
    CBT と国試は分野の切り方が違い（国試側は出題基準の区分が過去問に付かない
    ため暫定分類）、混ぜると同名の分野に両方の問題が入って演習しにくい。
    未指定なら従来どおり全部を返す。
    """

    def get(self, request):
        visible = Question.objects.visible_to(request.user)
        exam_type = request.query_params.get("exam_type")
        if exam_type:
            visible = visible.filter(exam_type=exam_type)
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

        results.sort(key=lambda r: category_sort_key(r["category"], exam_type or "CBT"))
        return Response(CategoryProgressSerializer(results, many=True).data)


class QuestionPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    # QuestionPicker needs the whole category at once for its mastery-filter
    # chips; categories are far below this bound.
    max_page_size = 500


class QuestionListView(APIView):
    """GET: 演習用の公開問題一覧 / POST: ユーザー問題の作成 (spec フェーズ7)."""

    throttle_scope = "question-create"

    def get_throttles(self):
        if self.request.method == "POST":
            return [ScopedRateThrottle()]
        return []

    def post(self, request):
        if not request.user.student_verified:
            raise exceptions.PermissionDenied("問題の作成には学生証認証が必要です。")
        serializer = UserQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        university = None
        if serializer.validated_data.get("visibility") == Question.Visibility.UNIVERSITY_ONLY:
            if not request.user.university_id:
                raise exceptions.ValidationError("学内限定にするには所属大学の設定が必要です。")
            # クライアント指定を信用せず作成者の所属で強制上書き (spec フェーズ7)
            university = request.user.university

        question = serializer.save(
            creator=request.user,
            source=Question.Source.USER,
            status=Question.Status.DRAFT,
            university=university,
        )
        return Response(UserQuestionSerializer(question).data, status=201)

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

        history_by_question = {
            row.question_id: row
            for row in latest.filter(question_id__in=[q.id for q in page])
        }
        serializer = QuestionSerializer(
            page, many=True, context={"history_by_question": history_by_question}
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


class MyQuestionsView(APIView):
    """自分が作成した問題の一覧（下書き/審査中/公開の管理, spec フェーズ7）。"""

    def get(self, request):
        qs = Question.objects.filter(creator=request.user).order_by("-created_at")
        return Response(UserQuestionSerializer(qs, many=True).data)


class QuestionDetailView(APIView):
    """PATCH/DELETE は作成者本人と moderator のみ (spec フェーズ7)。

    既に解答履歴がある問題（answer_count > 0）は本文の破壊的編集を禁止し、
    解説の追記のみ許可する。
    """

    EXPLANATION_ONLY_FIELDS = {"explanation"}

    def _get_editable(self, request, question_id):
        question = get_object_or_404(Question, pk=question_id)
        if question.creator_id != request.user.id and not request.user.is_moderator:
            raise exceptions.PermissionDenied("編集できるのは作成者かモデレーターのみです。")
        return question

    def patch(self, request, question_id):
        question = self._get_editable(request, question_id)
        if question.answer_count > 0:
            extra = set(request.data.keys()) - self.EXPLANATION_ONLY_FIELDS
            if extra:
                raise exceptions.ValidationError(
                    "解答履歴のある問題は本文を編集できません（解説の追記のみ可能）。"
                )
        serializer = UserQuestionSerializer(question, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # 公開済み問題の本文編集は再審査に回す（作成者による差し替え防止）
        content_changed = bool(set(request.data.keys()) - self.EXPLANATION_ONLY_FIELDS)
        if (
            question.status == Question.Status.PUBLISHED
            and content_changed
            and not request.user.is_moderator
        ):
            serializer.save(status=Question.Status.PENDING)
        else:
            serializer.save()
        return Response(UserQuestionSerializer(question).data)

    def delete(self, request, question_id):
        question = self._get_editable(request, question_id)
        if question.answer_count > 0 and not request.user.is_moderator:
            raise exceptions.ValidationError(
                "解答履歴のある問題は削除できません（モデレーターに依頼してください）。"
            )
        question.delete()
        return Response(status=204)


class QuestionSubmitForReviewView(APIView):
    """POST .../submit/ — 下書きを審査待ちにする (spec フェーズ7)."""

    def post(self, request, question_id):
        question = get_object_or_404(Question, pk=question_id, creator=request.user)
        if question.status != Question.Status.DRAFT:
            raise exceptions.ValidationError("下書きのみ提出できます。")
        question.status = Question.Status.PENDING
        question.save(update_fields=["status"])
        return Response(UserQuestionSerializer(question).data)


class QuestionReportView(APIView):
    """通報 (spec フェーズ7): 同一問題に3人以上の通報が付いたら自動で
    pending に戻し出題から外す。"""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "question-report"

    def post(self, request, question_id):
        question = get_object_or_404(
            Question.objects.visible_to(request.user), pk=question_id
        )
        reason = request.data.get("reason")
        if reason not in QuestionReport.Reason.values:
            raise exceptions.ValidationError(
                f"reason は {', '.join(QuestionReport.Reason.values)} のいずれか"
            )
        if QuestionReport.objects.filter(question=question, reporter=request.user).exists():
            raise exceptions.ValidationError("この問題はすでに通報済みです。")
        QuestionReport.objects.create(
            question=question,
            reporter=request.user,
            reason=reason,
            detail=request.data.get("detail", ""),
        )
        report_count = question.reports.count()
        if (
            report_count >= QuestionReport.AUTO_UNPUBLISH_THRESHOLD
            and question.status == Question.Status.PUBLISHED
        ):
            question.status = Question.Status.PENDING
            question.save(update_fields=["status"])
        return Response({"reported": True, "report_count": report_count}, status=201)


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
