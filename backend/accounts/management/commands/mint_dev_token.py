import datetime
import uuid

import jwt
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "DEV ONLY: mint a Supabase-compatible HS256 access token signed with "
        "SUPABASE_JWT_SECRET, for exercising the API with curl when no real "
        "Supabase project is wired up. The API will auto-provision a Profile "
        "for the token's sub on first use."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", default="dev@example.com")
        parser.add_argument(
            "--sub",
            default=None,
            help="UUID for the user (defaults to a UUID derived from --email)",
        )
        parser.add_argument("--minutes", type=int, default=60 * 24)

    def handle(self, *args, **options):
        if not settings.SUPABASE_JWT_SECRET:
            raise CommandError("Set SUPABASE_JWT_SECRET (any string works for local dev).")
        if not settings.DEBUG:
            raise CommandError("Refusing to mint dev tokens with DJANGO_DEBUG=false.")

        sub = options["sub"] or str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"dev-token:{options['email']}")
        )
        now = datetime.datetime.now(datetime.UTC)
        token = jwt.encode(
            {
                "sub": sub,
                "aud": settings.SUPABASE_JWT_AUDIENCE,
                "email": options["email"],
                "role": "authenticated",
                "iat": now,
                "exp": now + datetime.timedelta(minutes=options["minutes"]),
                "user_metadata": {},
            },
            settings.SUPABASE_JWT_SECRET,
            algorithm="HS256",
        )
        self.stdout.write(token)
