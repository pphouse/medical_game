"""ランキング集計 (spec フェーズ3).

    python manage.py aggregate_rankings --period all
    python manage.py aggregate_rankings --period 2026-07

算出定義 (spec 3-2, 曖昧さ排除のため厳密に):
- 解いた問題数 = ユニーク question_id 数（同じ問題を何度解いても1）
- 正答率 = 各問題の「初回解答」のみを分母とした正解率（周回の水増し防止）。
  ユニーク解答問題数 >= 100 のユーザーのみ対象
- 月間 = answered_at が対象月内の解答のみで上記2軸を計算
- 大学別 = 対象メンバー（学生証認証済み かつ 期間内10問以上）の平均正答率、
  および大学としてのユニーク解答問題数（メンバー解答の question_id の和集合）。
  対象メンバー5人未満の大学は除外
- ランキングの解答数には solo/review のみ含める（battle/mock の連打防止。
  context 列はフェーズ4で追加され、このフィルタが有効になる）

結果は RankingSnapshot に (scope, university, period, metric) 単位で
洗い替え保存する（トランザクション内 delete+insert による upsert）。
"""

import calendar
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from accounts.models import Profile
from exams.constants import (
    MIN_QUESTIONS_FOR_ACCURACY_RANKING,
    MIN_UNIVERSITY_MEMBERS,
    UNIVERSITY_MEMBER_MIN_SOLVED,
)
from exams.models import RankingSnapshot

# ランキングに数えるのは solo/review のみ（battle/mock の水増し防止, spec 4-2）
RANKED_CONTEXTS = ("solo", "review")


def month_bounds(period):
    year, month = map(int, period.split("-"))
    start = datetime.datetime(year, month, 1, tzinfo=datetime.UTC)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime.datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=datetime.UTC)
    return start, end


def fetch_user_stats(period):
    """ユーザーごとの (unique_solved, first_attempt_accuracy%) を SQL 一発で返す。

    初回解答は DISTINCT ON (user_id, question_id) ORDER BY answered_at で確定。
    """
    where = "WHERE context = ANY(%s)"
    params = [list(RANKED_CONTEXTS)]
    if period != "all":
        start, end = month_bounds(period)
        where += " AND answered_at >= %s AND answered_at <= %s"
        params += [start, end]

    sql = f"""
        SELECT user_id,
               COUNT(*) AS solved,
               ROUND(AVG(CASE WHEN correct THEN 1.0 ELSE 0.0 END) * 100, 1) AS accuracy
        FROM (
            SELECT DISTINCT ON (user_id, question_id)
                   user_id, question_id, correct
            FROM quiz_answerhistory
            {where}
            ORDER BY user_id, question_id, answered_at ASC, id ASC
        ) first_attempts
        GROUP BY user_id
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return {
            row[0]: {"solved": int(row[1]), "accuracy": float(row[2])}
            for row in cursor.fetchall()
        }


def fetch_university_unique_solved(period, member_ids):
    """大学メンバー全体でのユニーク解答問題数（question_id の和集合）。"""
    if not member_ids:
        return 0
    where = "WHERE user_id = ANY(%s) AND context = ANY(%s)"
    params = [list(member_ids), list(RANKED_CONTEXTS)]
    if period != "all":
        start, end = month_bounds(period)
        where += " AND answered_at >= %s AND answered_at <= %s"
        params += [start, end]
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(DISTINCT question_id) FROM quiz_answerhistory {where}", params
        )
        return int(cursor.fetchone()[0])


def ranked(entries, key):
    """value降順で並べ、同値は同順位（competition ranking）。"""
    entries = sorted(entries, key=key, reverse=True)
    result = []
    prev_value, prev_rank = None, 0
    for i, entry in enumerate(entries, start=1):
        value = key(entry)
        rank = prev_rank if value == prev_value else i
        result.append((rank, entry))
        prev_value, prev_rank = value, rank
    return result


class Command(BaseCommand):
    help = "RankingSnapshot を再集計する（全期間は日次、当月は毎時での実行を想定）"

    def add_arguments(self, parser):
        parser.add_argument("--period", default="all", help='"all" または "YYYY-MM"')

    @transaction.atomic
    def handle(self, *args, **options):
        period = options["period"]
        if period != "all":
            try:
                month_bounds(period)
            except (ValueError, IndexError):
                raise CommandError('period は "all" か "YYYY-MM" 形式') from None

        now = timezone.now()
        stats = fetch_user_stats(period)
        # 演習数ランキングは「1問も解いていない」ユーザーも対象に含める
        # （0問として最下位に並べる。ランキングに出ないと「順位不明」に見えて
        # しまうため）。正答率は従来どおり100問ゲートで絞られるので、
        # 0問のユーザーはこの後の accuracy フィルタで自然に除外される。
        # AI（対戦の代役プロフィール）はここには一切登場させない。
        profiles = {
            p.id: p
            for p in Profile.objects.filter(is_ai=False).select_related("university")
        }
        zero_stats = {"solved": 0, "accuracy": 0.0}

        rows = []

        def snapshot(scope, metric, *, profile=None, university=None, university_target=None,
                     rank=0, value=0.0, sample_size=0):
            rows.append(
                RankingSnapshot(
                    scope=scope,
                    metric=metric,
                    period=period,
                    profile=profile,
                    university=university,
                    university_target=university_target,
                    rank=rank,
                    value=value,
                    sample_size=sample_size,
                    computed_at=now,
                )
            )

        # --- 個人: 全国 + 学内 ---------------------------------------------
        individuals = [
            (profile, stats.get(pid, zero_stats)) for pid, profile in profiles.items()
        ]

        def build_individual(scope, university, members):
            # solved: 全員が対象
            for rank, (profile, s) in ranked(members, key=lambda m: m[1]["solved"]):
                snapshot(
                    scope,
                    RankingSnapshot.Metric.SOLVED,
                    profile=profile,
                    university=university,
                    rank=rank,
                    value=float(s["solved"]),
                    sample_size=s["solved"],
                )
            # accuracy: 100問ゲート (spec 3-2)
            eligible = [
                m for m in members if m[1]["solved"] >= MIN_QUESTIONS_FOR_ACCURACY_RANKING
            ]
            for rank, (profile, s) in ranked(eligible, key=lambda m: m[1]["accuracy"]):
                snapshot(
                    scope,
                    RankingSnapshot.Metric.ACCURACY,
                    profile=profile,
                    university=university,
                    rank=rank,
                    value=s["accuracy"],
                    sample_size=s["solved"],
                )

        build_individual(RankingSnapshot.Scope.NATIONAL, None, individuals)

        by_university = {}
        for profile, s in individuals:
            if profile.university_id:
                by_university.setdefault(profile.university_id, []).append((profile, s))
        for members in by_university.values():
            build_individual(
                RankingSnapshot.Scope.UNIVERSITY,
                members[0][0].university,
                members,
            )

        # --- 大学別（大学を1単位とする集計ランキング） -----------------------
        aggregates = []
        for members in by_university.values():
            eligible = [
                (p, s)
                for p, s in members
                if p.student_verified and s["solved"] >= UNIVERSITY_MEMBER_MIN_SOLVED
            ]
            if len(eligible) < MIN_UNIVERSITY_MEMBERS:
                continue
            avg_accuracy = round(
                sum(s["accuracy"] for _, s in eligible) / len(eligible), 1
            )
            unique_solved = fetch_university_unique_solved(
                period, [p.id for p, _ in eligible]
            )
            aggregates.append(
                {
                    "university": eligible[0][0].university,
                    "members": len(eligible),
                    "accuracy": avg_accuracy,
                    "solved": unique_solved,
                }
            )

        for metric in (RankingSnapshot.Metric.SOLVED, RankingSnapshot.Metric.ACCURACY):
            for rank, agg in ranked(aggregates, key=lambda a: a[metric]):
                snapshot(
                    RankingSnapshot.Scope.UNIVERSITY_AGGREGATE,
                    metric,
                    university_target=agg["university"],
                    rank=rank,
                    value=float(agg[metric]),
                    sample_size=agg["members"],
                )

        # --- 洗い替え upsert -------------------------------------------------
        RankingSnapshot.objects.filter(period=period).delete()
        RankingSnapshot.objects.bulk_create(rows, batch_size=1000)

        self.stdout.write(
            self.style.SUCCESS(
                f"aggregate_rankings period={period}: {len(rows)} snapshot rows "
                f"({len(individuals)} users, {len(aggregates)} universities)"
            )
        )
