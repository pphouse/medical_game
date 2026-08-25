import datetime
import uuid

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import Profile, University
from exams.management.commands.aggregate_rankings import fetch_user_stats
from exams.models import RankingSnapshot
from quiz.models import AnswerHistory, Question

from .helpers import auth_client

pytestmark = pytest.mark.django_db


def make_questions(n, category="循環器"):
    questions = Question.objects.bulk_create(
        Question(
            category=category,
            exam_type="CBT",
            difficulty=2,
            question_text=f"設問{category}{i}",
            choices=[{"key": k, "text": f"選択肢{k}"} for k in "ABCDE"],
            correct_choice_key="A",
            explanation="解説",
            status=Question.Status.PUBLISHED,
        )
        for i in range(n)
    )
    return questions


def make_profile(**kwargs):
    return Profile.objects.create(id=uuid.uuid4(), **kwargs)


def seed_answers(profile, questions, correct=True):
    AnswerHistory.objects.bulk_create(
        AnswerHistory(
            user=profile,
            question=q,
            mastery_level="circle" if correct else "cross",
            correct=correct,
            response_time_ms=5000,
        )
        for q in questions
    )


class TestAggregationDefinitions:
    def test_solved_counts_unique_questions_and_accuracy_uses_first_attempt(self):
        questions = make_questions(2)
        profile = make_profile(display_name="太郎")

        # q0: 1回目は不正解 → 2回目で正解（周回）。q1: 1回で正解。
        seed_answers(profile, [questions[0]], correct=False)
        seed_answers(profile, [questions[0]], correct=True)
        seed_answers(profile, [questions[1]], correct=True)

        stats = fetch_user_stats("all")[profile.id]
        assert stats["solved"] == 2  # 同じ問題を何度解いても1 (spec 3-2)
        assert stats["accuracy"] == 50.0  # 初回解答のみ: q0=誤, q1=正

    def test_monthly_period_only_counts_that_month(self):
        questions = make_questions(3)
        profile = make_profile()
        seed_answers(profile, questions, correct=True)
        AnswerHistory.objects.filter(user=profile, question=questions[0]).update(
            answered_at="2026-06-15T00:00:00Z"
        )
        AnswerHistory.objects.exclude(question=questions[0]).filter(user=profile).update(
            answered_at="2026-07-10T00:00:00Z"
        )

        assert fetch_user_stats("2026-07")[profile.id]["solved"] == 2
        assert fetch_user_stats("2026-06")[profile.id]["solved"] == 1


class TestAccuracyGate:
    def test_100_question_gate(self):
        questions = make_questions(120)
        qualified = make_profile(display_name="百問解いた人")
        unqualified = make_profile(display_name="99問の人")
        seed_answers(qualified, questions[:100], correct=True)
        seed_answers(unqualified, questions[:99], correct=True)

        call_command("aggregate_rankings", "--period", "all")

        accuracy_profiles = set(
            RankingSnapshot.objects.filter(
                scope="national", metric="accuracy", period="all"
            ).values_list("profile_id", flat=True)
        )
        assert qualified.id in accuracy_profiles
        assert unqualified.id not in accuracy_profiles

        # solved には両方載る
        solved_profiles = set(
            RankingSnapshot.objects.filter(
                scope="national", metric="solved", period="all"
            ).values_list("profile_id", flat=True)
        )
        assert {qualified.id, unqualified.id} <= solved_profiles

    def test_api_explains_ineligibility_reason(self):
        questions = make_questions(42)
        client, profile = auth_client(display_name="がんばる人")
        seed_answers(profile, questions, correct=True)
        call_command("aggregate_rankings", "--period", "all")

        res = client.get("/api/ranking/?scope=national&metric=accuracy&period=all")
        me = res.json()["me"]
        assert me["eligible"] is False
        assert "100問以上" in me["reason"]
        assert "現在 42問" in me["reason"]

    def test_api_returns_me_and_no_email(self):
        questions = make_questions(10)
        client, profile = auth_client(display_name="ランカー")
        seed_answers(profile, questions, correct=True)
        call_command("aggregate_rankings", "--period", "all")

        res = client.get("/api/ranking/?scope=national&metric=solved&period=all")
        body = res.json()
        assert body["me"]["rank"] == 1
        assert body["entries"][0]["display_name"] == "ランカー"
        assert body["entries"][0]["is_me"] is True
        assert "@" not in res.content.decode()  # メールアドレスは絶対に返さない


class TestUniversityAggregate:
    def test_universities_below_member_threshold_are_excluded(self):
        questions = make_questions(12)
        big = University.objects.create(name="大所帯大学")
        small = University.objects.create(name="少人数大学")

        for i in range(5):
            member = make_profile(
                display_name=f"big{i}", university=big, student_verified=True
            )
            seed_answers(member, questions[:10], correct=True)
        for i in range(4):
            member = make_profile(
                display_name=f"small{i}", university=small, student_verified=True
            )
            seed_answers(member, questions[:10], correct=True)

        call_command("aggregate_rankings", "--period", "all")

        ranked = set(
            RankingSnapshot.objects.filter(
                scope="university_aggregate", metric="accuracy", period="all"
            ).values_list("university_target__name", flat=True)
        )
        assert "大所帯大学" in ranked
        assert "少人数大学" not in ranked

    def test_unverified_members_do_not_count(self):
        questions = make_questions(12)
        uni = University.objects.create(name="未認証だらけ大学")
        for i in range(5):
            member = make_profile(
                display_name=f"m{i}", university=uni, student_verified=(i == 0)
            )
            seed_answers(member, questions[:10], correct=True)

        call_command("aggregate_rankings", "--period", "all")
        assert not RankingSnapshot.objects.filter(
            scope="university_aggregate", university_target=uni
        ).exists()


class TestInternalEndpoint:
    def test_rejects_bad_token(self, client):
        res = client.post(
            "/api/internal/aggregate/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": "wrong"},
        )
        assert res.status_code in (401, 403)

    def test_runs_aggregation_with_valid_token(self, client, settings):
        questions = make_questions(3)
        profile = make_profile()
        seed_answers(profile, questions, correct=True)

        res = client.post(
            "/api/internal/aggregate/",
            data='{"periods": ["all"]}',
            content_type="application/json",
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        assert res.status_code == 200
        assert RankingSnapshot.objects.filter(period="all").exists()


class TestLazyRefresh:
    """本番にはバッチを回すスケジューラが無く、RankingSnapshot が一度
    集計された時点で凍結していた。後から演習した人がいつまでもランキングに
    出てこない、という不具合の回帰テスト (exams/ranking_refresh.py)。"""

    def test_new_learner_appears_without_running_the_batch(self):
        questions = make_questions(3)
        veteran = make_profile(display_name="先輩")
        seed_answers(veteran, questions, correct=True)
        call_command("aggregate_rankings", "--period", "all", verbosity=0)
        # 「誰かが一度手で集計したきり放置」の状態。以降バッチは一切回さない。
        RankingSnapshot.objects.update(
            computed_at=timezone.now() - datetime.timedelta(days=3)
        )

        newcomer = make_profile(display_name="新人")
        seed_answers(newcomer, questions[:2], correct=True)

        client, _ = auth_client(newcomer)
        res = client.get("/api/ranking/?scope=national&metric=solved")
        assert res.status_code == 200
        assert res.data["me"]["rank"] == 2
        names = [e["display_name"] for e in res.data["entries"]]
        assert "新人" in names

    def test_home_summary_also_refreshes(self):
        questions = make_questions(3)
        veteran = make_profile(display_name="先輩")
        seed_answers(veteran, questions, correct=True)
        call_command("aggregate_rankings", "--period", "all", verbosity=0)
        RankingSnapshot.objects.update(
            computed_at=timezone.now() - datetime.timedelta(days=3)
        )

        newcomer = make_profile(display_name="新人")
        seed_answers(newcomer, questions[:2], correct=True)

        client, _ = auth_client(newcomer)
        res = client.get("/api/quiz/summary/")
        assert res.status_code == 200
        assert res.data["national_rank"]["rank"] == 2

    def test_fresh_snapshot_is_not_recomputed(self, settings):
        settings.RANKING_SNAPSHOT_TTL_SECONDS = 3600
        questions = make_questions(2)
        profile = make_profile(display_name="太郎")
        seed_answers(profile, questions, correct=True)
        call_command("aggregate_rankings", "--period", "all", verbosity=0)
        computed_at = RankingSnapshot.objects.filter(period="all").first().computed_at

        client, _ = auth_client(profile)
        client.get("/api/ranking/?scope=national&metric=solved")

        after = RankingSnapshot.objects.filter(period="all").first().computed_at
        assert after == computed_at  # TTL 内なので集計し直さない

    def test_negative_ttl_disables_lazy_refresh(self, settings):
        # 外部スケジューラで回す運用に切り替えたときの逃げ道。
        settings.RANKING_SNAPSHOT_TTL_SECONDS = -1
        questions = make_questions(2)
        profile = make_profile(display_name="太郎")
        seed_answers(profile, questions, correct=True)

        client, _ = auth_client(profile)
        res = client.get("/api/ranking/?scope=national&metric=solved")
        assert res.status_code == 200
        assert not RankingSnapshot.objects.exists()
