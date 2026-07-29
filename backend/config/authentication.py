"""DRF authentication against Supabase Auth JWTs.

The frontend obtains an access token from Supabase Auth (supabase-js) and
sends it as ``Authorization: Bearer <access_token>``. Two signing schemes
are supported and auto-detected from the token's ``alg`` header:

* **Asymmetric (recommended)** — ``RS256`` / ``ES256`` signed with the
  project's Supabase Auth *signing keys*. The public keys are fetched from
  the project JWKS endpoint (``SUPABASE_JWKS_URL``, derived from
  ``SUPABASE_URL``) and cached in-process; the private key never leaves
  Supabase, so a leaked backend env can't mint tokens.
* **Legacy HS256** — the shared ``SUPABASE_JWT_SECRET``. Kept for local
  development and projects that haven't migrated to signing keys.

Either way the token is verified locally (JWKS keys are cached, so there's
no per-request network round-trip) and an ``accounts.Profile`` keyed by the
``sub`` claim is auto-provisioned on first contact. ``request.user`` in API
views is therefore an ``accounts.Profile`` instance, NOT ``accounts.User``
(which only backs the /admin/ site).
"""

import jwt
from django.conf import settings
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from rest_framework import authentication, exceptions

# Asymmetric algorithms we accept from Supabase signing keys. HS256 is
# handled separately with the shared secret.
ASYMMETRIC_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")

_jwks_client = None


def _get_jwks_client():
    """Return a cached ``PyJWKClient`` for the project JWKS URL (or None)."""
    global _jwks_client
    if _jwks_client is None and settings.SUPABASE_JWKS_URL:
        _jwks_client = PyJWKClient(
            settings.SUPABASE_JWKS_URL, cache_keys=True, lifespan=600
        )
    return _jwks_client


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
        token = header[1].decode("latin-1")

        key, algorithms = self._resolve_key(token)
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=settings.SUPABASE_JWT_AUDIENCE,
                options={"require": ["sub", "aud", "exp"]},
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.") from None
        except InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token.") from None

        profile = self._get_or_create_profile(payload)
        return (profile, payload)

    def _resolve_key(self, token):
        """Pick the verification key + allowed algorithms from the header.

        The ``alg`` header is untrusted, but it only *selects* which key to
        verify against — ``jwt.decode`` still cryptographically checks the
        signature and pins ``algorithms`` so an attacker can't downgrade to
        ``none`` or swap an RS key in as an HS secret.
        """
        try:
            alg = jwt.get_unverified_header(token).get("alg")
        except InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token.") from None

        if alg in ASYMMETRIC_ALGORITHMS:
            client = _get_jwks_client()
            if client is None:
                raise exceptions.AuthenticationFailed(
                    "Server is not configured for asymmetric JWT verification "
                    "(set SUPABASE_URL or SUPABASE_JWKS_URL)."
                )
            try:
                signing_key = client.get_signing_key_from_jwt(token)
            except (PyJWKClientError, InvalidTokenError):
                raise exceptions.AuthenticationFailed(
                    "Unable to resolve the token signing key."
                ) from None
            return signing_key.key, [alg]

        if alg == "HS256":
            if not settings.SUPABASE_JWT_SECRET:
                raise exceptions.AuthenticationFailed(
                    "Server is not configured for Supabase auth "
                    "(SUPABASE_JWT_SECRET missing)."
                )
            return settings.SUPABASE_JWT_SECRET, ["HS256"]

        raise exceptions.AuthenticationFailed(f"Unsupported token algorithm: {alg}.")

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
