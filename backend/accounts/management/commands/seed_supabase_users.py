from django.core.management.base import BaseCommand

from accounts.provisioning import ensure_profile, supabase_admin_configured

# 表示名は実在の人名を避けてニックネームにする（accounts.nicknames と
# 同じ方針）。デモのスクリーンショットがそのまま実在の人物の名前に
# 見えてしまうため。
DEMO_USERS = [
    # (email, display_name, university, grade, verified)
    ("demo1@example.com", "ねむい", "サンプル医科大学", 4, True),
    ("demo2@example.com", "国試たすけて", "サンプル医科大学", 4, True),
    ("demo3@example.com", "ちくわ", "東京大学", 3, True),
    ("demo4@example.com", "3浪医", "京都大学", 5, False),
]

DEMO_PASSWORD = "demo-password-123"


class Command(BaseCommand):
    help = (
        "Provision demo users. With SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY set, "
        "creates real auth.users via the Admin API (so they can log in from the "
        "frontend); otherwise creates local-only Profile rows for display data."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Provision a single user with this email")
        parser.add_argument("--password", default=DEMO_PASSWORD)
        parser.add_argument("--display-name", default="")
        parser.add_argument("--university", default=None)
        parser.add_argument("--grade", type=int, default=None)
        parser.add_argument(
            "--verified", action="store_true", help="Mark student_verified=True"
        )

    def handle(self, *args, **options):
        if not supabase_admin_configured():
            self.stdout.write(
                self.style.WARNING(
                    "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set: creating "
                    "local-only Profile rows (these cannot sign in)."
                )
            )

        if options["email"]:
            profile = ensure_profile(
                email=options["email"],
                password=options["password"],
                display_name=options["display_name"],
                university_name=options["university"],
                grade=options["grade"],
                student_verified=options["verified"],
            )
            self.stdout.write(self.style.SUCCESS(f"Provisioned {profile.id} ({options['email']})"))
            return

        for email, name, university, grade, verified in DEMO_USERS:
            profile = ensure_profile(
                email=email,
                password=DEMO_PASSWORD,
                display_name=name,
                university_name=university,
                grade=grade,
                student_verified=verified,
            )
            self.stdout.write(f"  {email} / {DEMO_PASSWORD}  -> {profile.id}")

        self.stdout.write(self.style.SUCCESS(f"Provisioned {len(DEMO_USERS)} demo users."))
