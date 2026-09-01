"""ランキングの順位をクリックしたときの詳細画面。

- distribution: 母集団の「演習数×正答率」散布図（自分の位置を強調表示できる
  よう is_me を付ける）
- daily: 自分の直近30日分の演習数（solo/review のみ、ランキングと同じ集計
  対象）
- yesterday: 昨日の演習数と、一昨日との差分

RankingSnapshot は "all" 期間のスナップショットしか保持しない（洗い替え）ため、
過去日ごとの順位までは遡れない。ここで出せるのは「現在の順位」と「日々の
演習数」までで、日ごとの順位推移は出さない。
"""

import datetime

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RankingSnapshot
from .ranking_utils import grade_ranked_rows

DAILY_HISTORY_DAYS = 30
# ランキング集計と同じ対象（対戦・模試の連打を含めない）。
RANKED_CONTEXTS = ("solo", "review")


class RankDetailView(APIView):
    """GET /api/ranking/detail/?scope=national|university&metric=solved|accuracy

    RankingView と同じく同学年の中での順位・分布にする（対戦ランクとは違う
    問題演習だけの特別扱い。詳しくは ranking_utils のコメント参照）。
    """

    def get(self, request):
        scope = request.query_params.get("scope", RankingSnapshot.Scope.NATIONAL)
        metric = request.query_params.get("metric", RankingSnapshot.Metric.SOLVED)
        if scope not in (RankingSnapshot.Scope.NATIONAL, RankingSnapshot.Scope.UNIVERSITY):
            raise exceptions.ValidationError("scope が不正です")
        if metric not in RankingSnapshot.Metric.values:
            raise exceptions.ValidationError("metric が不正です")

        profile = request.user
        qs = RankingSnapshot.objects.filter(scope=scope, period="all", metric=metric)
        if scope == RankingSnapshot.Scope.UNIVERSITY:
            if not profile.university_id:
                return Response(
                    {
                        "me": {"eligible": False, "reason": "学内ランキングには所属大学の設定が必要です。"},
                        "distribution": [],
                        "daily": self._daily_history(profile),
                        "yesterday": self._yesterday(profile),
                    }
                )
            qs = qs.filter(university_id=profile.university_id)

        if profile.grade is None:
            return Response(
                {
                    "me": {"eligible": False, "reason": "学年が未設定です。マイページから設定してください。"},
                    "distribution": [],
                    "daily": self._daily_history(profile),
                    "yesterday": self._yesterday(profile),
                }
            )

        ranked_rows = grade_ranked_rows(qs, profile.grade)
        total = len(ranked_rows)
        match = next((r for r in ranked_rows if r[1].profile_id == profile.id), None)
        me = (
            {
                "eligible": True,
                "rank": match[0],
                "value": match[1].value,
                "out_of": total,
                "percentile": round((match[0] / total) * 100, 1) if total else None,
            }
            if match
            else {"eligible": False, "reason": "まだランキングの対象になっていません。"}
        )

        return Response(
            {
                "me": me,
                "distribution": self._distribution(scope, profile),
                "daily": self._daily_history(profile),
                "yesterday": self._yesterday(profile),
            }
        )

    def _distribution(self, scope, profile):
        """演習数×正答率の散布図。同学年・両方のスナップショットが揃っている
        プロフィールだけを対象にする（正答率は100問未満だと存在しない）。"""
        base = {"scope": scope, "period": "all", "profile__grade": profile.grade}
        if scope == RankingSnapshot.Scope.UNIVERSITY:
            base["university_id"] = profile.university_id

        solved_by_profile = dict(
            RankingSnapshot.objects.filter(
                metric=RankingSnapshot.Metric.SOLVED, **base
            ).values_list("profile_id", "value")
        )
        accuracy_by_profile = dict(
            RankingSnapshot.objects.filter(
                metric=RankingSnapshot.Metric.ACCURACY, **base
            ).values_list("profile_id", "value")
        )

        return [
            {
                "solved": int(solved_by_profile[pid]),
                "accuracy": accuracy_by_profile[pid],
                "is_me": pid == profile.id,
            }
            for pid in accuracy_by_profile
            if pid in solved_by_profile
        ]

    def _daily_history(self, profile):
        """直近30日、自分の演習数（solo/review）。"""
        since = timezone.now() - datetime.timedelta(days=DAILY_HISTORY_DAYS - 1)
        rows = (
            profile.answer_histories.filter(
                context__in=RANKED_CONTEXTS, answered_at__gte=since
            )
            .annotate(day=TruncDate("answered_at"))
            .values("day")
            .annotate(count=Count("id"))
        )
        counts_by_day = {row["day"]: row["count"] for row in rows}

        today = timezone.localdate()
        return [
            {
                "date": (today - datetime.timedelta(days=offset)).isoformat(),
                "count": counts_by_day.get(
                    today - datetime.timedelta(days=offset), 0
                ),
            }
            for offset in range(DAILY_HISTORY_DAYS - 1, -1, -1)
        ]

    def _yesterday(self, profile):
        today = timezone.localdate()
        yesterday = today - datetime.timedelta(days=1)
        day_before = today - datetime.timedelta(days=2)

        def count_on(day):
            return profile.answer_histories.filter(
                context__in=RANKED_CONTEXTS, answered_at__date=day
            ).count()

        count = count_on(yesterday)
        return {
            "date": yesterday.isoformat(),
            "count": count,
            "diff": count - count_on(day_before),
        }
