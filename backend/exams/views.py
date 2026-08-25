"""Ranking API (spec フェーズ3) + Mock-exam API (spec フェーズ5) + internal hook."""

import hmac

from django.conf import settings
from django.core.management import call_command
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from accounts.ranktier import compute_tier, tier_for_top_fraction
from exams.constants import MIN_QUESTIONS_FOR_ACCURACY_RANKING
from exams.grading import apply_irt_score, grade_single_result
from exams.models import MockAnswer, MockExam, MockResult, RankingSnapshot
from exams.ranking_refresh import ensure_fresh
from quiz.serializers import QuestionSerializer

DISPLAY_NAME_FALLBACK = "匿名ユーザー"
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def current_period():
    return timezone.localtime().strftime("%Y-%m")


class RankingView(APIView):
    """GET /api/ranking/?scope=national|university|university_aggregate
                        &metric=solved|accuracy&period=all|YYYY-MM&limit=50

    レスポンスは entries に加えて自分の順位 (me) を必ず含める (spec 3-3)。
    メールアドレスは絶対に返さない。表示名未設定は「匿名ユーザー」。
    """

    def get(self, request):
        scope = request.query_params.get("scope", RankingSnapshot.Scope.NATIONAL)
        metric = request.query_params.get("metric", RankingSnapshot.Metric.SOLVED)
        period = request.query_params.get("period", "all")
        try:
            limit = min(int(request.query_params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        except ValueError:
            raise exceptions.ValidationError("limit は整数で指定してください") from None

        if scope not in RankingSnapshot.Scope.values:
            raise exceptions.ValidationError("scope が不正です")
        if metric not in RankingSnapshot.Metric.values:
            raise exceptions.ValidationError("metric が不正です")

        # スナップショットが古ければここで集計し直す。本番にはバッチを回す
        # スケジューラが無く、放っておくと順位が凍結するため（ranking_refresh）。
        ensure_fresh(period)

        profile = request.user
        qs = RankingSnapshot.objects.filter(scope=scope, period=period, metric=metric)

        if scope == RankingSnapshot.Scope.UNIVERSITY:
            if not profile.university_id:
                return Response(
                    {
                        "entries": [],
                        "me": {
                            "rank": None,
                            "value": None,
                            "eligible": False,
                            "reason": "学内ランキングには所属大学の設定が必要です。",
                        },
                        "computed_at": None,
                    }
                )
            qs = qs.filter(university_id=profile.university_id)

        entries_qs = qs.select_related(
            "profile", "profile__university", "university_target"
        ).order_by("rank", "-value")[:limit]

        if scope == RankingSnapshot.Scope.UNIVERSITY_AGGREGATE:
            entries = [
                {
                    "rank": row.rank,
                    "university": row.university_target.name if row.university_target else None,
                    "value": row.value,
                    "sample_size": row.sample_size,
                    "is_me": bool(
                        profile.university_id
                        and row.university_target_id == profile.university_id
                    ),
                }
                for row in entries_qs
            ]
        else:
            entries = [
                {
                    "rank": row.rank,
                    "display_name": (
                        (row.profile.display_name or DISPLAY_NAME_FALLBACK)
                        if row.profile
                        else DISPLAY_NAME_FALLBACK
                    ),
                    "university": (
                        row.profile.university.name
                        if row.profile and row.profile.university
                        else None
                    ),
                    "value": row.value,
                    "is_me": row.profile_id == profile.id,
                }
                for row in entries_qs
            ]

        me = self._build_me(profile, scope, metric, period, qs)
        computed_at = qs.values_list("computed_at", flat=True).first()
        return Response({"entries": entries, "me": me, "computed_at": computed_at})

    def _build_me(self, profile, scope, metric, period, qs):
        # total: 母集団のサイズ。フロントの「上位X%」表示に使う（spec: パーセンタイルは
        # 常にランキング画面と同じ「厳密に自分より上の人数/母集団」の考え方に揃える）。
        total = qs.count()

        if scope == RankingSnapshot.Scope.UNIVERSITY_AGGREGATE:
            if not profile.university_id:
                return {
                    "rank": None,
                    "value": None,
                    "eligible": False,
                    "reason": "所属大学が未設定です。",
                    "total": total,
                }
            row = qs.filter(university_target_id=profile.university_id).first()
            if row:
                return {
                    "rank": row.rank,
                    "value": row.value,
                    "eligible": True,
                    "reason": None,
                    "total": total,
                }
            return {
                "rank": None,
                "value": None,
                "eligible": False,
                "reason": "対象メンバーが5人未満のため、大学ランキングの対象外です。",
                "total": total,
            }

        row = qs.filter(profile=profile).first()
        if row:
            return {
                "rank": row.rank,
                "value": row.value,
                "eligible": True,
                "reason": None,
                "total": total,
            }

        if metric == RankingSnapshot.Metric.ACCURACY:
            solved_row = RankingSnapshot.objects.filter(
                scope=scope,
                period=period,
                metric=RankingSnapshot.Metric.SOLVED,
                profile=profile,
            )
            if scope == RankingSnapshot.Scope.UNIVERSITY:
                solved_row = solved_row.filter(university_id=profile.university_id)
            solved = int(solved_row.values_list("value", flat=True).first() or 0)
            if solved < MIN_QUESTIONS_FOR_ACCURACY_RANKING:
                return {
                    "rank": None,
                    "value": None,
                    "eligible": False,
                    "reason": (
                        f"正答率ランキングは{MIN_QUESTIONS_FOR_ACCURACY_RANKING}問以上の解答が"
                        f"必要です（現在 {solved}問）"
                    ),
                    "total": total,
                }
        return {"rank": None, "value": None, "eligible": True, "reason": None, "total": total}


class ExamRankingHistoryView(APIView):
    """GET /api/ranking/exams/ — 自分の模試順位の履歴 (spec 3-3)。"""

    def get(self, request):
        results = (
            MockResult.objects.filter(user=request.user)
            .select_related("mock_exam")
            .order_by("-mock_exam__start_at")
        )
        return Response(
            [
                {
                    "mock_exam_id": r.mock_exam_id,
                    "title": r.mock_exam.title,
                    "kind": r.mock_exam.kind,
                    "exam_type": r.mock_exam.exam_type,
                    "start_at": r.mock_exam.start_at,
                    "score": r.score,
                    "rank": r.rank,
                    "university_rank": r.university_rank,
                    "deviation_score": r.deviation_score,
                    "points_delta": r.points_delta,
                    "irt_scaled_score": r.irt_scaled_score,
                    "submitted": r.submitted_at is not None,
                }
                for r in results
                if r.submitted_at is not None or r.mock_exam.kind != MockExam.Kind.CBT_ONCE
            ]
        )


class PointsRankingView(APIView):
    """GET /api/ranking/points/?scope=national|university&limit=50 —
    対戦＋模試（週次/月次）合算ポイントのランキングとランク階層
    （SS/S/A/B/C/D, spec: 上位5/25/40/60/80/100%）。

    scope=university は「同じ大学内での順位」に絞るが、各人のランク階層
    バッチはあくまで全国母集団での位置（tier はランキング画面の他の指標と
    同様、常に全国基準）。対象は ranked_matches>=1 のユーザーのみ
    （一度もランク付き対戦・模試をしていないユーザーは母集団にも含めない）。
    AI対戦相手のプロフィールは除外。
    """

    def get(self, request):
        try:
            limit = min(int(request.query_params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        except ValueError:
            raise exceptions.ValidationError("limit は整数で指定してください") from None
        scope = request.query_params.get("scope", "national")
        if scope not in ("national", "university"):
            raise exceptions.ValidationError("scope が不正です")

        national_qs = Profile.objects.filter(is_ai=False, ranked_matches__gte=1)
        total = national_qs.count()

        def tier_of(p):
            strictly_better = national_qs.filter(points__gt=p.points).count()
            return tier_for_top_fraction(strictly_better / total) if total else None

        if scope == "university":
            if not request.user.university_id:
                return Response(
                    {
                        "entries": [],
                        "me": {
                            "points": request.user.points,
                            "tier": None,
                            "ranked_matches": request.user.ranked_matches,
                            "eligible": False,
                            "reason": "学内ランキングには所属大学の設定が必要です。",
                        },
                        "total_ranked": total,
                    }
                )
            listing_qs = national_qs.filter(university_id=request.user.university_id)
        else:
            listing_qs = national_qs

        listing_qs = listing_qs.select_related("university")
        ordered = listing_qs.order_by("-points", "id")[:limit]
        entries = [
            {
                "rank": i,
                "display_name": p.display_name or DISPLAY_NAME_FALLBACK,
                "university": p.university.name if p.university else None,
                "points": p.points,
                "tier": tier_of(p),
                "is_me": p.id == request.user.id,
            }
            for i, p in enumerate(ordered, start=1)
        ]

        my_tier = compute_tier(request.user) if not request.user.is_ai else None
        return Response(
            {
                "entries": entries,
                "me": {
                    "points": request.user.points,
                    "tier": my_tier,
                    "ranked_matches": request.user.ranked_matches,
                    "eligible": my_tier is not None,
                },
                "total_ranked": total,
            }
        )


# --------------------------------------------------------------------------
# Mock exams (spec フェーズ5)
# --------------------------------------------------------------------------


def exam_status_for(exam, result, now=None):
    """CBT模試（生涯1回）は受験者ごとに完了タイミングが違うため、この模試
    インスタンス全体の状態ではなく個人の提出有無で見かけ上のステータスを返す。"""
    if exam.kind == MockExam.Kind.CBT_ONCE:
        if result and result.submitted_at:
            return MockExam.Status.GRADED
        return MockExam.Status.OPEN
    return exam.effective_status(now)


def exam_payload(exam, result=None, now=None):
    data = {
        "id": exam.id,
        "title": exam.title,
        "kind": exam.kind,
        "exam_type": exam.exam_type,
        "start_at": exam.start_at,
        "end_at": exam.end_at,
        "status": exam_status_for(exam, result, now),
        "question_count": exam.question_count,
        "duration_minutes": exam.duration_minutes,
        "target_grade_min": exam.target_grade_min,
        "target_grade_max": exam.target_grade_max,
        "my_result": None,
    }
    if result:
        data["my_result"] = {
            "started_at": result.started_at,
            "submitted_at": result.submitted_at,
            "deadline": result.deadline() if result.started_at else None,
        }
    return data


class ExamListView(APIView):
    """GET /api/exams/ — status・対象学年でフィルタ (spec フェーズ5)."""

    def get(self, request):
        now = timezone.now()
        qs = MockExam.objects.order_by("-start_at")
        status_filter = request.query_params.get("status")
        grade = request.user.grade
        my_results = {
            r.mock_exam_id: r for r in MockResult.objects.filter(user=request.user)
        }
        rows = []
        for exam in qs:
            if grade is not None:
                if exam.target_grade_min and grade < exam.target_grade_min:
                    continue
                if exam.target_grade_max and grade > exam.target_grade_max:
                    continue
            payload = exam_payload(exam, my_results.get(exam.id), now)
            if status_filter and payload["status"] != status_filter:
                continue
            rows.append(payload)
        return Response(rows)


class ExamStartView(APIView):
    """POST /api/exams/{id}/start/ — MockResult 作成。二重受験不可 (spec フェーズ5)。

    CBT模試（kind=cbt_once）は「いつでも受験できるが生涯1回だけ」なので、
    この模試インスタンスに限らず kind=cbt_once の受験歴があれば拒否する。
    """

    def post(self, request, exam_id):
        exam = get_object_or_404(MockExam, pk=exam_id)
        if not exam.is_open_for(request.user.grade):
            raise exceptions.ValidationError("この模試は現在受験できません。")
        if exam.kind == MockExam.Kind.CBT_ONCE:
            if MockResult.objects.filter(
                user=request.user, mock_exam__kind=MockExam.Kind.CBT_ONCE
            ).exists():
                raise exceptions.ValidationError(
                    "CBT模試はすでに受験済みです（生涯1回のみ受験できます）。"
                )
        elif MockResult.objects.filter(user=request.user, mock_exam=exam).exists():
            raise exceptions.ValidationError("すでに受験を開始しています（二重受験不可）。")
        result = MockResult.objects.create(
            user=request.user, mock_exam=exam, started_at=timezone.now()
        )
        return Response(exam_payload(exam, result), status=201)


def get_my_open_result(request, exam_id):
    exam = get_object_or_404(MockExam, pk=exam_id)
    result = MockResult.objects.filter(user=request.user, mock_exam=exam).first()
    if result is None or result.started_at is None:
        raise exceptions.ValidationError("受験を開始していません。")
    return exam, result


class ExamQuestionsView(APIView):
    """GET /api/exams/{id}/questions/ — MockQuestion 順。正解・解説は返さない
    （QuestionSerializer が除外を担保, spec 6 セキュリティ）。"""

    def get(self, request, exam_id):
        exam, result = get_my_open_result(request, exam_id)
        questions = [
            mq.question
            for mq in exam.mock_questions.select_related(
                "question", "question__question_set"
            ).order_by("order")
        ]
        answers = {
            a.question_id: a.selected_choice_key for a in result.answers.all()
        }
        return Response(
            {
                "deadline": result.deadline(),
                "submitted_at": result.submitted_at,
                "questions": QuestionSerializer(questions, many=True).data,
                "my_answers": answers,
            }
        )


class ExamAnswerView(APIView):
    """POST /api/exams/{id}/answers/ — MockAnswer を upsert（採点結果は返さ
    ない）。時間超過後・提出後は拒否 (spec フェーズ5)."""

    def post(self, request, exam_id):
        exam, result = get_my_open_result(request, exam_id)
        if result.submitted_at is not None:
            raise exceptions.ValidationError("提出済みのため変更できません。")
        if timezone.now() > result.deadline():
            raise exceptions.ValidationError("制限時間を超過しています。")

        question_id = request.data.get("question_id")
        selected = request.data.get("selected_choice_key", "")
        if not question_id:
            raise exceptions.ValidationError("question_id は必須です。")
        if not exam.mock_questions.filter(question_id=question_id).exists():
            raise exceptions.ValidationError("この模試の設問ではありません。")

        MockAnswer.objects.update_or_create(
            mock_result=result,
            question_id=question_id,
            defaults={
                "selected_choice_key": selected,
                "response_time_ms": int(request.data.get("response_time_ms", 0) or 0),
            },
        )
        return Response({"saved": True, "answered": result.answers.count()})


class ExamSubmitView(APIView):
    """POST /api/exams/{id}/submit/ — submitted_at 記録。以後変更不可。

    CBT模試（生涯1回）は受験者ごとに終了タイミングが違い、他の受験者の
    終了を待つ共有の締切がないため、提出と同時にこの1件だけを個別採点する
    （通常の週次/月次/大型模試は grade_mock_exam のバッチ採点を待つ）。
    """

    def post(self, request, exam_id):
        exam, result = get_my_open_result(request, exam_id)
        if result.submitted_at is None:
            result.submitted_at = timezone.now()
            result.save(update_fields=["submitted_at"])
            if exam.kind == MockExam.Kind.CBT_ONCE:
                self._grade_cbt_once(exam, result)
        return Response({"submitted_at": result.submitted_at})

    def _grade_cbt_once(self, exam, result):
        correct_questions = {
            mq.question_id: mq.question
            for mq in exam.mock_questions.select_related("question")
        }
        grade_single_result(result, correct_questions)
        apply_irt_score(result, correct_questions)

        # 参考値としての順位/偏差値: これまでにこの模試を終えた受験者との
        # 比較（全体の締切を待たず、この受験者1件だけを確定させる簡易版）。
        prior = list(
            MockResult.objects.filter(
                mock_exam__kind=MockExam.Kind.CBT_ONCE, submitted_at__isnull=False
            ).exclude(pk=result.pk)
        )
        cohort = prior + [result]
        scores = [r.score for r in cohort]
        n = len(scores)
        below = sum(1 for s in scores if s < result.score)
        result.percentile = round(below / n * 100, 1) if n else None
        result.rank = sum(1 for s in scores if s > result.score) + 1
        import statistics as _stats

        stdev = _stats.pstdev(scores) if n > 1 else 0
        mean = _stats.fmean(scores) if n else result.score
        result.deviation_score = round(50 + 10 * (result.score - mean) / stdev, 1) if stdev else 50.0

        result.save(
            update_fields=[
                "score", "section_scores", "irt_theta", "irt_scaled_score",
                "percentile", "rank", "deviation_score",
            ]
        )


class ExamResultView(APIView):
    """GET /api/exams/{id}/result/ — status=graded になるまで「採点中」。"""

    def get(self, request, exam_id):
        exam = get_object_or_404(MockExam, pk=exam_id)
        result = MockResult.objects.filter(user=request.user, mock_exam=exam).first()
        if exam_status_for(exam, result) != MockExam.Status.GRADED:
            return Response({"status": "grading", "message": "採点中です。しばらくお待ちください。"})
        if result is None:
            raise exceptions.NotFound("この模試の受験記録がありません。")

        total = MockResult.objects.filter(mock_exam=exam).count()
        review = [
            {
                "order": mq.order,
                "question_id": mq.question_id,
                "question_text": mq.question.question_text,
                "correct_choice_key": mq.question.correct_choice_key,
                "explanation": mq.question.explanation,
                "my_choice": next(
                    (
                        a.selected_choice_key
                        for a in result.answers.all()
                        if a.question_id == mq.question_id
                    ),
                    "",
                ),
            }
            for mq in exam.mock_questions.select_related("question").order_by("order")
        ]
        return Response(
            {
                "status": "graded",
                "title": exam.title,
                "kind": exam.kind,
                "exam_type": exam.exam_type,
                "score": result.score,
                "max_score": exam.mock_questions.count(),
                "rank": result.rank,
                "out_of": total,
                "university_rank": result.university_rank,
                "percentile": result.percentile,
                "deviation_score": result.deviation_score,
                "section_scores": result.section_scores,
                "section_deviation_scores": result.section_deviation_scores,
                "score_distribution": result.score_distribution or None,
                "points_delta": result.points_delta,
                "points_after": request.user.points if result.points_delta is not None else None,
                "tier_after": compute_tier(request.user) if result.points_delta is not None else None,
                "irt_theta": result.irt_theta,
                "irt_scaled_score": result.irt_scaled_score,
                "review": review,
            }
        )


class InternalAggregateView(APIView):
    """POST /api/internal/aggregate/ — pg_cron → Edge Function から叩かれる
    集計トリガ (spec 3-3 案A)。X-Internal-Token で保護。JWT 認証は使わない。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.headers.get("X-Internal-Token", "")
        if not settings.INTERNAL_API_TOKEN or not hmac.compare_digest(
            token, settings.INTERNAL_API_TOKEN
        ):
            raise exceptions.AuthenticationFailed("invalid internal token")

        periods = request.data.get("periods") or ["all", current_period()]
        for period in periods:
            call_command("aggregate_rankings", "--period", period)
        return Response({"status": "ok", "periods": periods})
