"""1日の目標・連続記録・学習リマインド（habits）。

日付は 2026年9月の週で組む。9/21（月）〜9/27（日）が ISO 週 39、
9/14（月）〜9/20（日）が週 38。「お休み」は週ごとに1日なので、週をまたぐ
かどうかが結果を変える。
"""

import datetime
import zoneinfo
from types import SimpleNamespace

import pytest
from django.db import DatabaseError
from django.utils import timezone

from accounts.models import NotificationPreference, Profile, PushSubscription
from habits import progress
from habits.models import DailyGoal, ReminderLog
from habits.progress import (
    MIN_RESPONSE_MS,
    ReminderExtras,
    habit_state,
    reminder_extras,
    reminder_plan,
    set_daily_goal,
    usual_hour,
)
from habits.reminders import send_due_reminders
from quiz.models import AnswerHistory, ReviewSchedule

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db

JST = zoneinfo.ZoneInfo("Asia/Tokyo")


def at(day, hour=12, minute=0):
    return datetime.datetime(2026, 9, day, hour, minute, tzinfo=JST)


@pytest.fixture
def clock(monkeypatch):
    """timezone.now() を止める。auto_now_add（解答・目標の時刻）もこれに従う。"""
    current = {"now": at(25)}
    monkeypatch.setattr(timezone, "now", lambda: current["now"])

    def set_now(value):
        current["now"] = value
        return value

    return set_now


@pytest.fixture
def questions():
    return [make_question(question_text=f"習慣テスト設問{i}") for i in range(12)]


def solve(profile, questions, when, *, context="solo", ms=5000):
    for question in questions:
        answer = AnswerHistory.objects.create(
            user=profile,
            question=question,
            mastery_level="circle",
            correct=True,
            response_time_ms=ms,
            context=context,
        )
        AnswerHistory.objects.filter(pk=answer.pk).update(answered_at=when)


def goal(profile, value, on_day):
    """on_day に目標を決めたことにする。"""
    return DailyGoal.objects.create(
        profile=profile, questions_per_day=value, effective_from=datetime.date(2026, 9, on_day)
    )


def new_profile(**kwargs):
    import uuid

    return Profile.objects.create(id=uuid.uuid4(), **kwargs)


class TestCounting:
    def test_counts_solo_and_review_only(self, clock, questions):
        profile = new_profile()
        goal(profile, 10, 1)
        solve(profile, questions[:2], at(25, 9))
        solve(profile, questions[2:3], at(25, 9), context="review")
        solve(profile, questions[3:4], at(25, 9), context="battle")
        solve(profile, questions[4:5], at(25, 9), context="mock")
        assert habit_state(profile).count == 3

    def test_same_question_counts_once_a_day(self, clock, questions):
        profile = new_profile()
        goal(profile, 10, 1)
        for hour in (8, 9, 10):
            solve(profile, questions[:1], at(24, hour))
        solve(profile, questions[:1], at(25, 8))
        state = habit_state(profile)
        assert state.counts == {datetime.date(2026, 9, 24): 1, datetime.date(2026, 9, 25): 1}

    def test_quick_answers_do_not_count(self, clock, questions):
        profile = new_profile()
        goal(profile, 10, 1)
        solve(profile, questions[:1], at(25, 9), ms=MIN_RESPONSE_MS - 1)
        solve(profile, questions[1:2], at(25, 9), ms=MIN_RESPONSE_MS)
        assert habit_state(profile).count == 1

    def test_day_changes_at_tokyo_midnight(self, clock, questions):
        profile = new_profile()
        goal(profile, 10, 1)
        solve(profile, questions[:1], at(24, 23, 59))
        solve(profile, questions[1:2], at(25, 0, 1))
        state = habit_state(profile)
        assert state.counts == {datetime.date(2026, 9, 24): 1, datetime.date(2026, 9, 25): 1}


class TestStreak:
    def run(self, profile, questions, plan, goal_value=2):
        """plan: {日: 解く問題数}。9/1 に目標を決めたことにする。"""
        goal(profile, goal_value, 1)
        for day, n in plan.items():
            solve(profile, questions[:n], at(day, 9))

    def test_consecutive_days(self, clock, questions):
        profile = new_profile()
        self.run(profile, questions, {22: 2, 23: 2, 24: 2})
        state = habit_state(profile)
        assert state.streak == 3
        assert not state.achieved

    def test_achieving_today_adds_one(self, clock, questions):
        profile = new_profile()
        self.run(profile, questions, {23: 2, 24: 2, 25: 2})
        assert habit_state(profile).streak == 3

    def test_one_missed_day_a_week_is_a_rest_day(self, clock, questions):
        profile = new_profile()
        # 月・火 達成、水 未達、木 達成 → 金曜の時点で3日（水はお休み）
        self.run(profile, questions, {21: 2, 22: 2, 23: 1, 24: 2})
        state = habit_state(profile)
        assert state.streak == 3
        assert not state.rest_available
        statuses = {d["date"].day: d["status"] for d in state.recent_days()}
        assert statuses[23] == "rest"
        assert statuses[25] == "today"

    def test_second_miss_in_the_same_week_breaks(self, clock, questions):
        profile = new_profile()
        self.run(profile, questions, {21: 2, 22: 1, 23: 2, 24: 0})
        assert habit_state(profile).streak == 0

    def test_rest_is_per_calendar_week(self, clock, questions):
        profile = new_profile()
        clock(at(22))
        # 金 達成、土 未達（週38のお休み）、日 達成、月 未達（週39のお休み）
        self.run(profile, questions, {18: 2, 19: 0, 20: 2, 21: 0})
        state = habit_state(profile)
        assert state.streak == 2
        assert not state.rest_available

    def test_missing_without_a_streak_keeps_the_rest_day(self, clock, questions):
        profile = new_profile()
        # 月 1問だけ（記録0なのでお休みは使わない）、火 達成、水 未達（お休み）、木 達成
        self.run(profile, questions, {21: 1, 22: 2, 23: 1, 24: 2})
        state = habit_state(profile)
        assert state.streak == 2
        statuses = {d["date"].day: d["status"] for d in state.recent_days()}
        assert statuses[21] == "missed"
        assert statuses[23] == "rest"

    def test_raising_the_goal_later_keeps_past_days(self, clock, questions):
        profile = new_profile()
        self.run(profile, questions, {22: 2, 23: 2, 24: 2})
        clock(at(25, 8))
        set_daily_goal(profile, 10)
        state = habit_state(profile)
        assert state.goal == 10
        assert state.streak == 3


class TestGoalApi:
    def test_first_goal_counts_earlier_study(self, clock, questions):
        client, profile = auth_client()
        for day in (22, 23, 24):
            solve(profile, questions[:5], at(day, 9))
        body = client.put("/api/habits/goal/", {"questions_per_day": 5}, format="json").json()
        assert body["goal"] == 5
        assert body["streak"] == 3
        assert body["effective_from"] == "2026-09-25"

    @pytest.mark.parametrize("value", [0, 101, "abc"])
    def test_rejects_out_of_range(self, clock, value):
        client, _ = auth_client()
        res = client.put("/api/habits/goal/", {"questions_per_day": value}, format="json")
        assert res.status_code == 400

    def test_raising_after_achieving_starts_tomorrow(self, clock, questions):
        client, profile = auth_client()
        client.put("/api/habits/goal/", {"questions_per_day": 5}, format="json")
        solve(profile, questions[:5], at(25, 9))
        body = client.put("/api/habits/goal/", {"questions_per_day": 10}, format="json").json()
        assert body["effective_from"] == "2026-09-26"
        assert body["goal"] == 5 and body["achieved"] is True
        assert body["upcoming_goal"] == {"questions_per_day": 10, "effective_from": "2026-09-26"}
        clock(at(26))
        assert client.get("/api/habits/today/").json()["goal"] == 10

    def test_raising_before_achieving_applies_today(self, clock, questions):
        client, profile = auth_client()
        client.put("/api/habits/goal/", {"questions_per_day": 5}, format="json")
        solve(profile, questions[:3], at(25, 9))
        body = client.put("/api/habits/goal/", {"questions_per_day": 10}, format="json").json()
        assert body["effective_from"] == "2026-09-25"
        assert body["goal"] == 10 and body["remaining"] == 7

    def test_lowering_applies_today_and_cancels_a_pending_raise(self, clock, questions):
        client, profile = auth_client()
        client.put("/api/habits/goal/", {"questions_per_day": 5}, format="json")
        solve(profile, questions[:5], at(25, 9))
        client.put("/api/habits/goal/", {"questions_per_day": 10}, format="json")  # 明日から
        body = client.put("/api/habits/goal/", {"questions_per_day": 3}, format="json").json()
        assert body["effective_from"] == "2026-09-25"
        assert body["goal"] == 3 and body["upcoming_goal"] is None

    def test_today_payload_shape(self, clock):
        client, _ = auth_client()
        body = client.get("/api/habits/today/").json()
        assert body["goal"] is None and body["streak"] == 0
        assert len(body["days"]) == 7 and body["days"][-1]["date"] == "2026-09-25"
        assert body["goal_choices"] == [5, 10, 20, 30, 50]
        assert body["reminder"] == {"enabled": False, "hour": 20}
        assert body["reminders"] == []


class TestAnswerProgress:
    def submit(self, client, question, ms=5000):
        return client.post(
            "/api/quiz/answers/",
            {"question_id": question.id, "selected_choice_key": "A", "response_time_ms": ms},
            format="json",
        ).json()

    def test_reports_progress_and_the_moment_of_achievement(self, clock, questions):
        client, _ = auth_client()
        client.put("/api/habits/goal/", {"questions_per_day": 3}, format="json")
        results = [self.submit(client, q)["daily_progress"] for q in questions[:4]]
        assert [p["count"] for p in results] == [1, 2, 3, 4]
        assert [p["remaining"] for p in results] == [2, 1, 0, 0]
        assert [p["just_achieved"] for p in results] == [False, False, True, False]
        assert results[2]["streak"] == 1
        assert "streak" not in results[3]

    def test_repeating_a_question_does_not_advance(self, clock, questions):
        client, _ = auth_client()
        client.put("/api/habits/goal/", {"questions_per_day": 3}, format="json")
        self.submit(client, questions[0])
        assert self.submit(client, questions[0])["daily_progress"]["count"] == 1

    def test_without_a_goal(self, clock, questions):
        client, _ = auth_client()
        progress_ = self.submit(client, questions[0])["daily_progress"]
        assert progress_["goal"] is None and progress_["count"] == 1
        assert progress_["just_achieved"] is False

    def test_failure_does_not_block_the_answer(self, clock, questions, monkeypatch):
        """本番で表を作る前にデプロイされても、解答は記録される。"""

        def broken(cls, profile):
            raise DatabaseError('relation "habits_dailygoal" does not exist')

        monkeypatch.setattr(progress.GoalTimeline, "for_profile", classmethod(broken))
        client, profile = auth_client()
        body = self.submit(client, questions[0])
        assert body["correct"] is True
        assert body["daily_progress"] is None
        assert AnswerHistory.objects.filter(user=profile).count() == 1


def reminder_setup(profile, *, hour=20, enabled=True):
    return NotificationPreference.objects.create(
        profile=profile, enabled=enabled, preferred_hour=hour, timezone="Asia/Tokyo"
    )


class TestReminderPlan:
    def plan(self, profile, now):
        pref = NotificationPreference.objects.get(profile=profile)
        return reminder_plan(habit_state(profile, now), reminder_extras(profile, now), pref, now)

    def test_daily_reminders_then_a_pause(self, clock, questions):
        profile = new_profile()
        clock(at(25, 8))
        set_daily_goal(profile, 5)
        reminder_setup(profile)
        plan = self.plan(profile, at(25, 8))
        assert [(r.at.day, r.at.hour, r.kind) for r in plan] == [
            (25, 20, "daily"),
            (26, 20, "daily"),
            (27, 20, "daily"),
            (28, 20, "daily"),
            (29, 20, "daily"),
            (30, 20, "daily"),
            (1, 20, "daily"),
            (2, 20, "paused"),
        ]
        assert len({r.id for r in plan}) == len(plan)

    def test_nothing_today_once_achieved(self, clock, questions):
        profile = new_profile()
        clock(at(25, 8))
        set_daily_goal(profile, 5)
        reminder_setup(profile)
        solve(profile, questions[:5], at(25, 7))
        plan = self.plan(profile, at(25, 8))
        assert plan[0].at.day == 26

    def test_evening_reminder_protects_a_streak(self, clock, questions):
        profile = new_profile()
        goal(profile, 2, 1)
        reminder_setup(profile)
        for day in (23, 24):
            solve(profile, questions[:2], at(day, 9))
        today = [r for r in self.plan(profile, at(25, 8)) if r.at.day == 25]
        assert [(r.at.hour, r.kind) for r in today] == [(20, "daily"), (21, "streak")]
        assert "連続2日" in today[1].title

    def test_no_evening_reminder_when_the_usual_one_is_late(self, clock, questions):
        profile = new_profile()
        goal(profile, 2, 1)
        reminder_setup(profile, hour=22)
        for day in (23, 24):
            solve(profile, questions[:2], at(day, 9))
        today = [r for r in self.plan(profile, at(25, 8)) if r.at.day == 25]
        assert [r.kind for r in today] == ["daily"]

    def test_stops_after_the_pause(self, clock, questions):
        profile = new_profile()
        clock(at(14, 9))
        set_daily_goal(profile, 2)
        solve(profile, questions[:2], at(14, 9))
        reminder_setup(profile)
        assert self.plan(profile, at(25, 8)) == []

    def test_started_today_says_how_many_are_left(self, clock, questions):
        profile = new_profile()
        goal(profile, 5, 1)
        reminder_setup(profile)
        solve(profile, questions[:2], at(25, 7))
        first = self.plan(profile, at(25, 8))[0]
        assert first.body == "あと3問で今日の5問です。"

    def test_review_template_links_to_the_review_deck(self, clock, questions):
        profile = new_profile()
        goal(profile, 5, 1)
        ReviewSchedule.objects.create(user=profile, question=questions[0], next_review_at=at(20))
        extras = reminder_extras(profile, at(25, 8))
        assert extras.due_reviews == 1
        pref = reminder_setup(profile)
        seen = {}
        for day in range(21, 28):  # 日ごとに文面が変わるので1週間ぶん見る
            clock(at(day, 8))
            state = habit_state(profile, at(day, 8))
            for r in progress.reminders_for_day(state, extras, pref, state.today):
                seen[r.template] = r.url
        assert seen.get("review") == "/review"

    def test_exam_countdown_only_for_the_national_exam(self, clock, settings):
        settings.NATIONAL_EXAM_DATE = "2027-02-06"
        kokushi = new_profile(exam_preference="KOKUSHI")
        cbt = new_profile(exam_preference="CBT")
        assert reminder_extras(kokushi).exam_days(datetime.date(2026, 9, 25)) == 134
        assert reminder_extras(cbt).exam_date is None
        assert (
            ReminderExtras(exam_date=datetime.date(2026, 9, 1)).exam_days(
                datetime.date(2026, 9, 25)
            )
            is None
        )

    def test_plan_is_in_the_payload_only_when_enabled(self, clock, questions):
        client, profile = auth_client()
        client.put("/api/habits/goal/", {"questions_per_day": 5}, format="json")
        assert client.get("/api/habits/today/").json()["reminders"] == []
        reminder_setup(profile)
        reminders = client.get("/api/habits/today/").json()["reminders"]
        assert reminders[0]["at"] == "2026-09-25T20:00:00+09:00"
        assert set(reminders[0]) == {"id", "at", "kind", "title", "body", "url"}


class TestSendReminders:
    @pytest.fixture
    def subscribed(self, clock, questions):
        profile = new_profile()
        goal(profile, 5, 1)
        solve(profile, questions[:1], at(24, 9))
        reminder_setup(profile)
        PushSubscription.objects.create(
            profile=profile,
            endpoint=f"https://push.example/{profile.id}",
            keys={"p256dh": "k", "auth": "a"},
        )
        return profile

    @staticmethod
    def collect(sent, fail_with=None):
        def sender(subscription, payload):
            if fail_with is not None:
                raise fail_with
            sent.append((subscription.endpoint, payload))

        return sender

    def test_sends_once_at_the_chosen_hour(self, subscribed):
        sent = []
        assert send_due_reminders(at(25, 19), sender=self.collect(sent)) == 0
        assert send_due_reminders(at(25, 20), sender=self.collect(sent)) == 1
        assert send_due_reminders(at(25, 20, 30), sender=self.collect(sent)) == 0
        assert len(sent) == 1
        assert set(sent[0][1]) == {"title", "body", "url"}
        assert ReminderLog.objects.filter(profile=subscribed, kind="daily").count() == 1

    def test_nothing_once_achieved(self, subscribed, questions):
        solve(subscribed, questions[:5], at(25, 9))
        sent = []
        assert send_due_reminders(at(25, 20), sender=self.collect(sent)) == 0

    def test_evening_streak_reminder(self, subscribed, questions):
        solve(subscribed, questions[:5], at(23, 9))
        solve(subscribed, questions[:5], at(24, 9))
        sent = []
        assert send_due_reminders(at(25, 21), sender=self.collect(sent)) == 1
        assert "連続2日" in sent[0][1]["title"]

    def test_dead_subscription_is_removed(self, subscribed):
        gone = Exception("gone")
        gone.response = SimpleNamespace(status_code=410)
        assert send_due_reminders(at(25, 20), sender=self.collect([], fail_with=gone)) == 0
        assert not PushSubscription.objects.filter(profile=subscribed).exists()

    def test_needs_a_vapid_key_to_really_send(self, subscribed, settings):
        settings.VAPID_PRIVATE_KEY = ""
        assert send_due_reminders(at(25, 20)) == 0

    def test_internal_endpoint_requires_the_token(self, subscribed, settings):
        from rest_framework.test import APIClient

        settings.VAPID_PRIVATE_KEY = ""
        client = APIClient()
        assert client.get("/api/internal/send-reminders/").status_code in (401, 403)
        res = client.post(
            "/api/internal/send-reminders/", HTTP_X_INTERNAL_TOKEN=settings.INTERNAL_API_TOKEN
        )
        assert res.status_code == 200 and res.json() == {"status": "ok", "sent": 0}


def test_web_push_waits_for_offline_browsers(monkeypatch, settings):
    """TTL 0（pywebpush の既定）だと、送った瞬間に閉じていたブラウザには届かない。"""
    import pywebpush

    from accounts.webpush import PUSH_TTL_SECONDS, send_web_push

    calls = []
    monkeypatch.setattr(pywebpush, "webpush", lambda **kwargs: calls.append(kwargs))
    settings.VAPID_PRIVATE_KEY = "k"
    subscription = SimpleNamespace(
        endpoint="https://push.example/x", keys={"p256dh": "p", "auth": "a"}
    )
    send_web_push(subscription, {"title": "t", "body": "b", "url": "/"})
    assert calls[0]["ttl"] == PUSH_TTL_SECONDS == 3 * 60 * 60


class TestUsualHour:
    def test_median_of_first_answers(self, clock, questions):
        profile = new_profile()
        for day, hour in ((22, 7), (23, 21), (24, 8)):
            solve(profile, questions[:1], at(day, hour))
            solve(profile, questions[1:2], at(day, 23))
        assert usual_hour(profile) == 8

    def test_needs_a_few_days(self, clock, questions):
        profile = new_profile()
        solve(profile, questions[:1], at(24, 7))
        assert usual_hour(profile) is None


def test_account_deletion_removes_goals_and_logs(clock, questions):
    client, profile = auth_client()
    goal(profile, 5, 1)
    ReminderLog.objects.create(
        profile=profile, sent_on=datetime.date(2026, 9, 24), kind="daily", template="start"
    )
    res = client.delete("/api/auth/me/", {"confirm": True}, format="json")
    assert res.status_code == 204
    assert not DailyGoal.objects.exists()
    assert not ReminderLog.objects.exists()
