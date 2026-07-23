import datetime
import uuid

import jwt
from django.conf import settings
from rest_framework.test import APIClient

from accounts.models import Profile


def make_token(
    sub=None,
    *,
    email="student@example.com",
    audience=None,
    secret=None,
    expires_in=3600,
    display_name=None,
):
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "sub": str(sub or uuid.uuid4()),
        "aud": audience if audience is not None else settings.SUPABASE_JWT_AUDIENCE,
        "email": email,
        "role": "authenticated",
        "iat": now,
        "exp": now + datetime.timedelta(seconds=expires_in),
    }
    if display_name is not None:
        payload["user_metadata"] = {"display_name": display_name}
    return jwt.encode(payload, secret or settings.SUPABASE_JWT_SECRET, algorithm="HS256")


def auth_client(profile=None, **profile_kwargs):
    """APIClient authenticated as `profile` (created if not given)."""
    if profile is None:
        profile = Profile.objects.create(id=uuid.uuid4(), **profile_kwargs)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token(profile.id)}")
    return client, profile
