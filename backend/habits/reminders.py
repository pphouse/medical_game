"""学習リマインドを Web Push で送る（毎時、Vercel Cron から）。

iOS アプリは端末内に予約するので、ここで送るのはブラウザで購読した人だけ。
何をいつ送るかは progress.reminders_for_day が決める（iOS と同じ決まり）。
同じ種類は1日1回まで（ReminderLog。同時に2本走っても一意制約で1通になる）。
"""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import NotificationPreference
from accounts.webpush import send_web_push

from .models import ReminderLog
from .progress import (
    STREAK_REMINDER_HOUR,
    habit_state,
    reminder_extras,
    reminder_timezone,
    reminders_for_day,
)

logger = logging.getLogger(__name__)


def send_due_reminders(now=None, sender=send_web_push):
    """今の時刻に送る通知を送って、送った通数を返す。"""
    if not settings.VAPID_PRIVATE_KEY and sender is send_web_push:
        logger.warning("VAPID_PRIVATE_KEY が未設定のため、学習リマインドを送りません")
        return 0
    now = now or timezone.now()
    sent = 0
    prefs = (
        NotificationPreference.objects.filter(
            enabled=True, profile__push_subscriptions__isnull=False
        )
        .distinct()
        .select_related("profile")
    )
    for pref in prefs:
        local_now = now.astimezone(reminder_timezone(pref))
        # 重い集計の前に、この時刻に送るものがありうるかだけ見る。
        if local_now.hour not in (pref.preferred_hour, STREAK_REMINDER_HOUR):
            continue
        profile = pref.profile
        state = habit_state(profile, now)
        reminders = reminders_for_day(state, reminder_extras(profile, now), pref, state.today)
        for reminder in reminders:
            if reminder.at.hour == local_now.hour and _deliver(
                profile, reminder, state.today, sender
            ):
                sent += 1
    return sent


def _deliver(profile, reminder, day, sender):
    try:
        with transaction.atomic():
            ReminderLog.objects.create(
                profile=profile, sent_on=day, kind=reminder.kind, template=reminder.template
            )
    except IntegrityError:
        return False  # 今日はもう送った
    payload = {"title": reminder.title, "body": reminder.body, "url": reminder.url}
    delivered = 0
    for subscription in list(profile.push_subscriptions.all()):
        try:
            sender(subscription, payload)
            delivered += 1
        except Exception as exc:  # noqa: BLE001 - pywebpush の例外は環境依存
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                subscription.delete()  # 解除されたブラウザの購読を掃除する
            else:
                logger.warning("push failed for %s: %s", profile.id, exc)
    return delivered > 0
