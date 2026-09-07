"""ランキングの順位をクリックしたときの詳細画面。

- distribution: 母集団の「演習数×正答率」散布図（自分の位置を強調表示できる
  よう is_me を付ける）
- daily: 自分の1ヶ月分（暦月）の演習数（solo/review のみ、ランキングと同じ
  集計対象）。?month=YYYY-MM で過去の月に遡れる
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

# ランキング集計と同じ対象（対戦・模試の連打を含めない）。
RANKED_CONTEXTS = ("solo", "review")


def month_bounds(month):
    """``datetime.date`` の (月初, 翌月初) を返す。"""
    first = month.replace(day=1)
    nxt = (
        first.replace(year=first.year + 1, month=1)
        if first.month == 12
        else first.replace(month=first.month + 1)
    )
    return first, nxt


def parse_month(raw, default):
    """'YYYY-MM' をその月の1日として読む。未指定・不正なら default の月。"""
    if not raw:
        return default.replace(day=1)
    try:
        year, month = (int(part) for part in raw.split("-", 1))
        return datetime.date(year, month, 1)
    except (ValueError, TypeError) as e:
        raise exceptions.ValidationError("month は YYYY-MM で指定してください") from e


class RankDetailView(APIView):
    """GET /api/ranking/detail/?scope=national|university&metric=solved|accuracy

    RankingView と同じく同学年の中での順位・分布にする（対戦ランクとは違う
    問題演習だけの特別扱い。詳しくは ranking_utils のコメント参照）。
    """

    def get(self, request):
        self.month = parse_month(
            request.query_params.get("month"), timezone.localdate()
        )
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
                        "daily_range": self._daily_range(profile),
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
                    "daily_range": self._daily_range(profile),
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
                "daily_range": self._daily_range(profile),
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
        """指定した月（既定は今月）の1日ごとの演習数（solo/review）。

        暦月で切るので「何年何月ぶんか」がはっきりし、前後の月へ遡れる。
        月末が来ていない今月ぶんは、まだ来ていない日も 0 として並べる
        （グラフの横幅が月の途中で伸び縮みしないようにするため）。
        """
        first, next_first = month_bounds(self.month)
        rows = (
            profile.answer_histories.filter(
                context__in=RANKED_CONTEXTS,
                answered_at__date__gte=first,
                answered_at__date__lt=next_first,
            )
            .annotate(day=TruncDate("answered_at"))
            .values("day")
            .annotate(count=Count("id"))
        )
        counts_by_day = {row["day"]: row["count"] for row in rows}

        days = (next_first - first).days
        return [
            {
                "date": (first + datetime.timedelta(days=offset)).isoformat(),
                "count": counts_by_day.get(first + datetime.timedelta(days=offset), 0),
            }
            for offset in range(days)
        ]

    def _daily_range(self, profile):
        """遡れる範囲。矢印を止める位置を決めるのに使う。

        下限は最初に解いた月（履歴が無ければ今月）、上限は今月。
        """
        first_answer = (
            profile.answer_histories.filter(context__in=RANKED_CONTEXTS)
            .order_by("answered_at")
            .values_list("answered_at", flat=True)
            .first()
        )
        today = timezone.localdate()
        earliest = (
            timezone.localtime(first_answer).date().replace(day=1)
            if first_answer
            else today.replace(day=1)
        )
        # 表示中の月が下限より古いこともある（URLで直接指定された場合）。
        earliest = min(earliest, self.month)
        return {
            "month": self.month.strftime("%Y-%m"),
            "earliest_month": earliest.strftime("%Y-%m"),
            "latest_month": today.strftime("%Y-%m"),
        }

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
