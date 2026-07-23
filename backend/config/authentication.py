"""DRF authentication against Supabase Auth JWTs.

The frontend obtains an access token from Supabase Auth (supabase-js) and
sends it as ``Authorization: Bearer <access_token>``. We verify it locally
with the project's legacy HS256 JWT secret (``SUPABASE_JWT_SECRET``) — no
network round-trip — and auto-provision an ``accounts.Profile`` row keyed
by ``auth.users.id`` (the ``sub`` claim) on first contact.

``request.user`` in API views is therefore an ``accounts.Profile``
instance, NOT ``accounts.User`` (which only backs the /admin/ site).
"""

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions


class SupabaseJWTAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed(
                "Invalid Authorization header. Expected 'Bearer <token>'."
            )

        if not settings.SUPABASE_JWT_SECRET:
            raise exceptions.AuthenticationFailed(
                "Server is not configured for Supabase auth (SUPABASE_JWT_SECRET missing)."
            )

        try:
            payload = jwt.decode(
                header[1],
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience=settings.SUPABASE_JWT_AUDIENCE,
                options={"require": ["sub", "aud", "exp"]},
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.") from None
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token.") from None

        profile = self._get_or_create_profile(payload)
        return (profile, payload)

    def authenticate_header(self, request):
        return self.keyword

    @staticmethod
    def _get_or_create_profile(payload):
        # Imported lazily so this module can be referenced in settings
        # without triggering app loading at import time.
        from accounts.models import Profile

        metadata = payload.get("user_metadata") or {}
        email = payload.get("email") or ""
        default_name = metadata.get("display_name") or (
            email.split("@", 1)[0] if email else ""
        )
        profile, _ = Profile.objects.get_or_create(
            id=payload["sub"],
            defaults={"display_name": default_name[:50]},
        )
        return profile
