"""Helpers to provision demo/seed users.

Two modes:

- Supabase mode (``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY`` set):
  creates real ``auth.users`` rows via the GoTrue Admin API so the seeded
  accounts can actually sign in from the frontend.
- Local fallback (no Supabase env): creates Profile rows only, with a
  deterministic UUID derived from the email. These cannot sign in — they
  exist purely to populate rankings/battles in development and tests.
"""

import uuid

import requests
from django.conf import settings

from .models import Profile, University

# Fixed namespace for deterministic local-fallback UUIDs (idempotent seeds).
_LOCAL_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def supabase_admin_configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)


def _admin_headers():
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def create_supabase_user(email, password, display_name=""):
    """Create (or fetch) an auth.users row via the Admin API. Returns its UUID."""
    base = settings.SUPABASE_URL.rstrip("/")
    resp = requests.post(
        f"{base}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"display_name": display_name},
        },
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return uuid.UUID(resp.json()["id"])
    # 422 = already registered; look the user up by email instead.
    if resp.status_code == 422:
        lookup = requests.get(
            f"{base}/auth/v1/admin/users",
            headers=_admin_headers(),
            params={"page": 1, "per_page": 200},
            timeout=15,
        )
        lookup.raise_for_status()
        for user in lookup.json().get("users", []):
            if user.get("email") == email:
                return uuid.UUID(user["id"])
    resp.raise_for_status()
    raise RuntimeError(f"Could not create or find Supabase user for {email}")


def ensure_profile(
    *,
    email,
    password="demo-password-123",
    display_name="",
    university_name=None,
    grade=None,
    student_verified=False,
    use_supabase=None,
):
    """Idempotently provision a Profile (and, if configured, an auth user)."""
    if use_supabase is None:
        use_supabase = supabase_admin_configured()

    if use_supabase:
        profile_id = create_supabase_user(email, password, display_name)
    else:
        profile_id = uuid.uuid5(_LOCAL_NS, f"medical-game:{email}")

    university = None
    if university_name:
        university, _ = University.objects.get_or_create(name=university_name)

    profile, _ = Profile.objects.update_or_create(
        id=profile_id,
        defaults={
            "display_name": display_name or email.split("@", 1)[0],
            "university": university,
            "grade": grade,
            "student_verified": student_verified,
        },
    )
    return profile
