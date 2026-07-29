"""学生証画像の保持期間クリーンアップ (spec フェーズ7). 日次実行を想定。

- 却下済みで画像が残っているもの → 削除
- 承認後 STUDENT_ID_RETENTION_DAYS (90日) を過ぎたもの → 削除
（個人情報の保持期間を最小化する）
"""

import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import StudentVerification
from accounts.storage import delete_student_id_image


class Command(BaseCommand):
    help = "却下済み・承認後90日経過の学生証画像を Storage から削除する"

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - datetime.timedelta(days=settings.STUDENT_ID_RETENTION_DAYS)

        targets = StudentVerification.objects.filter(
            image_deleted_at__isnull=True
        ).filter(
            models_q_rejected_or_expired(cutoff)
        )

        deleted = 0
        for verification in targets:
            if delete_student_id_image(verification.image_path):
                verification.image_deleted_at = now
                verification.save(update_fields=["image_deleted_at"])
                deleted += 1
        self.stdout.write(self.style.SUCCESS(f"deleted {deleted} student-id images"))


def models_q_rejected_or_expired(cutoff):
    from django.db.models import Q

    return Q(status=StudentVerification.Status.REJECTED) | Q(
        status=StudentVerification.Status.APPROVED, reviewed_at__lte=cutoff
    )
