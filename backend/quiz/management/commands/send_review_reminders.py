"""復習リマインド送信 (spec フェーズ6). 毎時実行を想定（cron / pg_cron→
Edge Function → internal API いずれでも可）。

対象: NotificationPreference.enabled=True のユーザーのうち、
  - ユーザーのタイムゾーンで現在時刻が preferred_hour に一致し、
  - next_review_at <= now の復習件数が閾値（既定5件）以上で、
  - 当日まだ送信していない（ReviewReminder で管理）
Push を許可していない（購読なしの）ユーザーには送らない — アプリ内
バッジのみ (spec)。dead subscription (404/410) は自動削除する。
"""

import json
import zoneinfo

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import NotificationPreference
from quiz.models import Question, ReviewReminder, ReviewSchedule

DEFAULT_THRESHOLD = 5


def default_sender(subscription, payload):
    """pywebpush で1通送る。テストでは差し替える。"""
    from pywebpush import webpush

    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": subscription.keys,
        },
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=settings.VAPID_PRIVATE_KEY,
        vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
    )


class Command(BaseCommand):
    help = "復習期限が来たユーザーに Web Push リマインドを送る（1日1回まで）"

    def add_arguments(self, parser):
        parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
        parser.add_argument(
            "--force-hour",
            action="store_true",
            help="preferred_hour に関係なく送る（テスト・手動実行用）",
        )

    def handle(self, *args, sender=default_sender, **options):
        if not settings.VAPID_PRIVATE_KEY and sender is default_sender:
            self.stdout.write(self.style.WARNING("VAPID_PRIVATE_KEY 未設定のため送信しません。"))
            return

        now = timezone.now()
        threshold = options["threshold"]
        sent_count = 0

        prefs = NotificationPreference.objects.filter(enabled=True).select_related("profile")
        for pref in prefs:
            try:
                local_now = now.astimezone(zoneinfo.ZoneInfo(pref.timezone))
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                local_now = timezone.localtime(now)
            if not options["force_hour"] and local_now.hour != pref.preferred_hour:
                continue

            profile = pref.profile
            due = ReviewSchedule.objects.filter(
                user=profile,
                next_review_at__lte=now,
                question__in=Question.objects.visible_to(profile),
            ).count()
            if due < threshold:
                continue

            already = ReviewReminder.objects.filter(
                profile=profile,
                channel=ReviewReminder.Channel.PUSH,
                sent_at__isnull=False,
                scheduled_for__date=local_now.date(),
            ).exists()
            if already:
                continue

            subscriptions = list(profile.push_subscriptions.all())
            if not subscriptions:
                continue  # Push 未許可 → アプリ内バッジのみ (spec)

            payload = {
                "title": "復習の時間です",
                "body": f"復習期限の問題が{due}問たまっています。今日のうちに片付けましょう！",
                "url": "/review",
            }
            delivered = 0
            for subscription in subscriptions:
                try:
                    sender(subscription, payload)
                    delivered += 1
                except Exception as exc:  # noqa: BLE001 - pywebpush 例外は環境依存
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status in (404, 410):
                        subscription.delete()  # dead endpoint を掃除
                    else:
                        self.stderr.write(f"push failed for {profile.id}: {exc}")

            if delivered:
                ReviewReminder.objects.create(
                    profile=profile,
                    scheduled_for=now,
                    channel=ReviewReminder.Channel.PUSH,
                    sent_at=timezone.now(),
                    question_count=due,
                )
                sent_count += 1

        self.stdout.write(self.style.SUCCESS(f"review reminders sent to {sent_count} users"))
