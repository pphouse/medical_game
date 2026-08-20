"""利用者のロールを変える。最初の管理者を作るための入口でもある。

管理画面のロール変更APIは IsAdmin で守っているため、管理者が1人もいない
状態では誰もロールを変えられない（鶏と卵）。最初の1人だけはここで作る。

    python manage.py set_role --display-name naoto --role admin
    python manage.py set_role --id dd68a251-... --role moderator
    python manage.py set_role --list
"""

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Profile


class Command(BaseCommand):
    help = "利用者のロール (student / moderator / admin) を変更する。"

    def add_arguments(self, parser):
        parser.add_argument("--id", help="プロフィールのUUID")
        parser.add_argument("--display-name", help="表示名（完全一致）")
        parser.add_argument(
            "--role",
            choices=[r for r, _ in Profile.Role.choices],
            help="付与するロール",
        )
        parser.add_argument(
            "--list", action="store_true", help="現在の一覧を表示して終了する"
        )

    def handle(self, *args, **options):
        if options["list"]:
            for p in Profile.objects.order_by("-role", "display_name"):
                self.stdout.write(f"{p.role:<10} {p.display_name or '(名前なし)':<24} {p.id}")
            return

        if not options["role"]:
            raise CommandError("--role を指定してください（--list で一覧）。")

        if options["id"]:
            qs = Profile.objects.filter(pk=options["id"])
        elif options["display_name"]:
            qs = Profile.objects.filter(display_name=options["display_name"])
        else:
            raise CommandError("--id か --display-name のどちらかを指定してください。")

        count = qs.count()
        if count == 0:
            raise CommandError("該当する利用者がいません（--list で確認）。")
        if count > 1:
            raise CommandError(
                f"{count}件が該当します。--id で1人に絞ってください（--list で確認）。"
            )

        profile = qs.get()
        before = profile.role
        profile.role = options["role"]
        profile.save(update_fields=["role"])
        self.stdout.write(
            self.style.SUCCESS(
                f"{profile.display_name or profile.id}: {before} -> {profile.role}"
            )
        )
