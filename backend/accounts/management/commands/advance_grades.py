"""毎年4月に全学生の学年を1つ繰り上げるバッチ。

    python manage.py advance_grades

学年（Profile.grade）は模試一覧のCBT/国試表示振り分け・大型模試の対象学年
判定にそのまま連動しているため、進級のたびに手動で直す必要がないよう
年度切り替え（4月1日）に合わせて自動実行する想定（Vercel Cron / pg_cron
から `POST /api/internal/advance-grades/` を叩く運用も可, spec:
docs/deploy-vercel.md の定期実行の項を参照）。

grade が 6（最終学年）のユーザーは繰り上げない（卒業/留年判定はこのバッチの
対象外。医学部は1〜6年）。grade 未設定のユーザーも対象外。
"""

from django.core.management.base import BaseCommand

from accounts.models import Profile

MAX_GRADE = 6


class Command(BaseCommand):
    help = "全プロフィールの学年（grade）を1つ繰り上げる（6年は据え置き、未設定は対象外）"

    def handle(self, *args, **options):
        qs = Profile.objects.filter(grade__isnull=False, grade__lt=MAX_GRADE)
        updated = 0
        # 大量更新でも1件ずつ+1するため bulk_update ではなく F式で一括更新する
        from django.db.models import F

        updated = qs.update(grade=F("grade") + 1)
        self.stdout.write(self.style.SUCCESS(f"{updated}人の学年を1つ繰り上げました。"))
