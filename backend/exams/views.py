"""Ranking API (spec フェーズ3) + internal aggregation hook.

模試 API 本体はフェーズ5で実装。
"""

import hmac

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from exams.constants import MIN_QUESTIONS_FOR_ACCURACY_RANKING
from exams.models import MockResult, RankingSnapshot

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
        if scope == RankingSnapshot.Scope.UNIVERSITY_AGGREGATE:
            if not profile.university_id:
                return {
                    "rank": None,
                    "value": None,
                    "eligible": False,
                    "reason": "所属大学が未設定です。",
                }
            row = qs.filter(university_target_id=profile.university_id).first()
            if row:
                return {"rank": row.rank, "value": row.value, "eligible": True, "reason": None}
            return {
                "rank": None,
                "value": None,
                "eligible": False,
                "reason": "対象メンバーが5人未満のため、大学ランキングの対象外です。",
            }

        row = qs.filter(profile=profile).first()
        if row:
            return {"rank": row.rank, "value": row.value, "eligible": True, "reason": None}

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
                }
        return {"rank": None, "value": None, "eligible": True, "reason": None}


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
                    "start_at": r.mock_exam.start_at,
                    "score": r.score,
                    "rank": r.rank,
                }
                for r in results
            ]
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
