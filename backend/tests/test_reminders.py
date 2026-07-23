import datetime
import zoneinfo

import pytest
from django.utils import timezone

from accounts.models import NotificationPreference, PushSubscription
from quiz.models import ReviewReminder, ReviewSchedule

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db


def make_due_reviews(profile, n):
    for i in range(n):
        question = make_question(question_text=f"復習設問{i}-{profile.id}")
        ReviewSchedule.objects.create(
            user=profile,
            question=question,
            next_review_at=timezone.now() - datetime.timedelta(hours=1),
        )


def setup_notifiable(profile, *, due=6, enabled=True, subscribed=True):
    make_due_reviews(profile, due)
    NotificationPreference.objects.create(
        profile=profile, enabled=enabled, preferred_hour=20, timezone="Asia/Tokyo"
    )
    if subscribed:
        PushSubscription.objects.create(
            profile=profile,
            endpoint=f"https://push.example/{profile.id}",
            keys={"p256dh": "k", "auth": "a"},
        )


def run_command(sent, *, force_hour=True, threshold=5, fail_with=None):
    from quiz.management.commands.send_review_reminders import Command

    def sender(subscription, payload):
        if fail_with is not None:
            raise fail_with
        sent.append((subscription.endpoint, payload))

    cmd = Command()
    cmd.handle(sender=sender, threshold=threshold, force_hour=force_hour)
    return cmd


class TestReviewSummary:
    def test_counts(self):
        client, profile = auth_client()
        make_due_reviews(profile, 3)
        # 明日が期限のものを1件
        q = make_question(question_text="明日の分")
        ReviewSchedule.objects.create(
            user=profile,
            question=q,
            next_review_at=timezone.localtime() + datetime.timedelta(days=1),
        )
        body = client.get("/api/quiz/review-deck/summary/").json()
        assert body["due_now"] == 3
        assert body["today"] == 3
        assert body["tomorrow"] == 1
        assert body["this_week"] >= 4


class TestSendReminders:
    def test_sends_once_per_day_over_threshold(self):
        _, profile = auth_client()
        setup_notifiable(profile, due=6)
        sent = []
        run_command(sent)
        assert len(sent) == 1
        assert "6問" in sent[0][1]["body"]
        reminder = ReviewReminder.objects.get(profile=profile)
        assert reminder.sent_at is not None
        assert reminder.question_count == 6

        # 同日2回目は送らない (1日1回まで)
        run_command(sent)
        assert len(sent) == 1
        assert ReviewReminder.objects.count() == 1

    def test_skips_below_threshold_disabled_and_unsubscribed(self):
        _, below = auth_client()
        setup_notifiable(below, due=4)
        _, disabled = auth_client()
        setup_notifiable(disabled, due=6, enabled=False)
        _, no_push = auth_client()
        setup_notifiable(no_push, due=6, subscribed=False)  # バッジのみ (spec)

        sent = []
        run_command(sent)
        assert sent == []
        assert ReviewReminder.objects.count() == 0

    def test_respects_preferred_hour(self):
        _, profile = auth_client()
        setup_notifiable(profile, due=6)
        pref = NotificationPreference.objects.get(profile=profile)
        now_tokyo = timezone.now().astimezone(zoneinfo.ZoneInfo("Asia/Tokyo"))
        pref.preferred_hour = (now_tokyo.hour + 1) % 24  # いまは送らない時刻
        pref.save()

        sent = []
        run_command(sent, force_hour=False)
        assert sent == []

        pref.preferred_hour = now_tokyo.hour
        pref.save()
        run_command(sent, force_hour=False)
        assert len(sent) == 1

    def test_dead_subscription_is_pruned(self):
        _, profile = auth_client()
        setup_notifiable(profile, due=6)

        class Response:
            status_code = 410

        class Gone(Exception):
            response = Response()

        sent = []
        run_command(sent, fail_with=Gone())
        assert sent == []
        assert PushSubscription.objects.count() == 0  # 410 は掃除される
        assert ReviewReminder.objects.count() == 0  # 配信0なら記録しない
