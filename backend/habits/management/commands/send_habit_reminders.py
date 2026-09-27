"""学習リマインドの Web Push を手で送る（本番は /api/internal/send-reminders/ を毎時）。"""

import datetime

from django.core.management.base import BaseCommand, CommandError

from habits.reminders import send_due_reminders


class Command(BaseCommand):
    help = "今の時刻に送る学習リマインドを Web Push で送る（同じ種類は1日1回まで）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--at",
            help="この時刻として送る（確認用。例: 2026-09-27T20:00+09:00）",
        )

    def handle(self, *args, **options):
        now = None
        if options["at"]:
            try:
                now = datetime.datetime.fromisoformat(options["at"])
            except ValueError as exc:
                raise CommandError(f"--at の形式が違います: {exc}") from None
            if now.tzinfo is None:
                raise CommandError("--at にはタイムゾーンを付けてください（例: +09:00）")
        sent = send_due_reminders(now)
        self.stdout.write(self.style.SUCCESS(f"habit reminders sent: {sent}"))
