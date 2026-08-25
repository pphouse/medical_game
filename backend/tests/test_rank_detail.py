import datetime

import pytest
from django.utils import timezone

from accounts.models import Profile, University
from exams.models import RankingSnapshot
from quiz.models import AnswerHistory, Question
from tests.helpers import auth_client


def make_question(**kwargs):
    defaults = dict(
        category="循環器",
        topic="",
        exam_type=Question.ExamType.CBT,
        difficulty=Question.Difficulty.NORMAL,
        question_text="問題",
        choices=[{"key": k, "text": k} for k in "ABCDE"],
        correct_choice_key="A",
        explanation="",
        visibility=Question.Visibility.PUBLIC,
        status=Question.Status.PUBLISHED,
    )
    defaults.update(kwargs)
    return Question.objects.create(**defaults)


def snapshot(profile, metric, value, rank, scope="national", university=None):
    RankingSnapshot.objects.create(
        scope=scope,
        university=university,
        period="all",
        metric=metric,
        profile=profile,
        rank=rank,
        value=value,
        computed_at=timezone.now(),
    )


@pytest.mark.django_db
class TestRankDetail:
    def test_me_reports_rank_and_percentile(self):
        client, profile = auth_client()
        other = Profile.objects.create(id="00000000-0000-0000-0000-000000000001")
        snapshot(profile, RankingSnapshot.Metric.SOLVED, value=100, rank=2)
        snapshot(other, RankingSnapshot.Metric.SOLVED, value=200, rank=1)

        body = client.get("/api/ranking/detail/?scope=national&metric=solved").json()
        assert body["me"]["eligible"] is True
        assert body["me"]["rank"] == 2
        assert body["me"]["out_of"] == 2
        assert body["me"]["percentile"] == 100.0

    def test_not_ranked_is_reported(self):
        client, profile = auth_client()
        body = client.get("/api/ranking/detail/?scope=national&metric=solved").json()
        assert body["me"]["eligible"] is False

    def test_university_scope_without_university_is_ineligible(self):
        client, profile = auth_client()
        body = client.get("/api/ranking/detail/?scope=university&metric=solved").json()
        assert body["me"]["eligible"] is False
        assert body["distribution"] == []

    def test_distribution_pairs_solved_and_accuracy_by_profile(self):
        client, profile = auth_client()
        other = Profile.objects.create(id="00000000-0000-0000-0000-000000000002")
        snapshot(profile, RankingSnapshot.Metric.SOLVED, value=120, rank=2)
        snapshot(profile, RankingSnapshot.Metric.ACCURACY, value=60.0, rank=2)
        snapshot(other, RankingSnapshot.Metric.SOLVED, value=300, rank=1)
        snapshot(other, RankingSnapshot.Metric.ACCURACY, value=80.0, rank=1)

        body = client.get("/api/ranking/detail/?scope=national&metric=solved").json()
        points = {(p["solved"], p["accuracy"], p["is_me"]) for p in body["distribution"]}
        assert points == {(120, 60.0, True), (300, 80.0, False)}

    def test_distribution_excludes_solved_only_profiles(self):
        """正答率スナップショットが無い（100問未満）ユーザーは散布図に出さない。"""
        client, profile = auth_client()
        other = Profile.objects.create(id="00000000-0000-0000-0000-000000000003")
        snapshot(profile, RankingSnapshot.Metric.SOLVED, value=50, rank=2)
        snapshot(profile, RankingSnapshot.Metric.ACCURACY, value=70.0, rank=1)
        snapshot(other, RankingSnapshot.Metric.SOLVED, value=10, rank=3)
        # other には ACCURACY のスナップショットが無い（100問未満）

        body = client.get("/api/ranking/detail/?scope=national&metric=solved").json()
        assert len(body["distribution"]) == 1
        assert body["distribution"][0]["is_me"] is True

    def test_university_scope_only_includes_same_university(self):
        client, profile = auth_client()
        u1 = University.objects.create(name="A大学")
        u2 = University.objects.create(name="B大学")
        profile.university = u1
        profile.save(update_fields=["university"])
        same = Profile.objects.create(
            id="00000000-0000-0000-0000-000000000004", university=u1
        )
        other_univ = Profile.objects.create(
            id="00000000-0000-0000-0000-000000000005", university=u2
        )
        snapshot(profile, RankingSnapshot.Metric.SOLVED, value=100, rank=1, scope="university", university=u1)
        snapshot(profile, RankingSnapshot.Metric.ACCURACY, value=90.0, rank=1, scope="university", university=u1)
        snapshot(same, RankingSnapshot.Metric.SOLVED, value=80, rank=2, scope="university", university=u1)
        snapshot(same, RankingSnapshot.Metric.ACCURACY, value=70.0, rank=2, scope="university", university=u1)
        snapshot(other_univ, RankingSnapshot.Metric.SOLVED, value=999, rank=1, scope="university", university=u2)
        snapshot(other_univ, RankingSnapshot.Metric.ACCURACY, value=99.0, rank=1, scope="university", university=u2)

        body = client.get("/api/ranking/detail/?scope=university&metric=solved").json()
        assert len(body["distribution"]) == 2
        assert all(p["solved"] != 999 for p in body["distribution"])

    def test_daily_history_covers_30_days_with_zero_fill(self):
        client, profile = auth_client()
        q = make_question()
        AnswerHistory.objects.create(
            user=profile,
            question=q,
            correct=True,
            mastery_level="circle",
            response_time_ms=1000,
            context="solo",
        )
        body = client.get("/api/ranking/detail/?scope=national&metric=solved").json()
        assert len(body["daily"]) == 30
        today = timezone.localdate().isoformat()
        assert body["daily"][-1]["date"] == today
        assert body["daily"][-1]["count"] == 1
        assert body["daily"][0]["count"] == 0

    def test_daily_history_excludes_battle_and_mock(self):
        client, profile = auth_client()
        q = make_question()
        AnswerHistory.objects.create(
            user=profile, question=q, correct=True, mastery_level="circle",
            response_time_ms=1000, context="battle",
        )
        body = client.get("/api/ranking/detail/?scope=national&metric=solved").json()
        assert body["daily"][-1]["count"] == 0

    def test_yesterday_diff_from_day_before(self):
        client, profile = auth_client()
        q1 = make_question()
        q2 = make_question()
        yesterday = timezone.now() - datetime.timedelta(days=1)
        day_before = timezone.now() - datetime.timedelta(days=2)

        h1 = AnswerHistory.objects.create(
            user=profile, question=q1, correct=True, mastery_level="circle",
            response_time_ms=1000, context="solo",
        )
        AnswerHistory.objects.filter(id=h1.id).update(answered_at=yesterday)

        h2 = AnswerHistory.objects.create(
            user=profile, question=q2, correct=True, mastery_level="circle",
            response_time_ms=1000, context="solo",
        )
        AnswerHistory.objects.filter(id=h2.id).update(answered_at=day_before)

        body = client.get("/api/ranking/detail/?scope=national&metric=solved").json()
        assert body["yesterday"]["count"] == 1
        assert body["yesterday"]["diff"] == 0

    def test_rejects_invalid_scope(self):
        client, _ = auth_client()
        res = client.get("/api/ranking/detail/?scope=university_aggregate")
        assert res.status_code == 400
