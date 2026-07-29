import uuid

import jwt
import pytest
from rest_framework.test import APIClient

from accounts.models import Profile, University

from .helpers import auth_client, make_token

pytestmark = pytest.mark.django_db


def test_request_without_token_is_rejected():
    res = APIClient().get("/api/quiz/summary/")
    assert res.status_code == 401


def test_valid_token_autoprovisions_profile():
    sub = uuid.uuid4()
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {make_token(sub, email='taro@example.com', display_name='太郎')}"
    )
    res = client.get("/api/auth/me/")
    assert res.status_code == 200
    assert res.json()["id"] == str(sub)
    profile = Profile.objects.get(id=sub)
    assert profile.display_name == "太郎"
    # Same sub on a later request maps to the same profile (no duplicates).
    res2 = client.get("/api/auth/me/")
    assert res2.json()["id"] == str(sub)
    assert Profile.objects.count() == 1


def test_display_name_falls_back_to_email_local_part():
    sub = uuid.uuid4()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token(sub, email='hanako@med.ac.jp')}")
    client.get("/api/auth/me/")
    assert Profile.objects.get(id=sub).display_name == "hanako"


@pytest.mark.parametrize(
    "token_kwargs",
    [
        {"expires_in": -60},  # expired
        {"audience": "wrong-audience"},
        {"secret": "some-other-secret"},
    ],
)
def test_bad_tokens_are_rejected(token_kwargs):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token(**token_kwargs)}")
    assert client.get("/api/auth/me/").status_code == 401


def test_garbage_token_is_rejected():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-jwt")
    assert client.get("/api/auth/me/").status_code == 401


def test_bootstrap_sets_initial_profile_fields():
    university = University.objects.create(name="テスト医科大学")
    client, profile = auth_client()
    res = client.post(
        "/api/auth/bootstrap/",
        {"display_name": "新入生", "university_id": university.id, "grade": 2},
        format="json",
    )
    assert res.status_code == 200
    profile.refresh_from_db()
    assert profile.display_name == "新入生"
    assert profile.university == university
    assert profile.grade == 2


def test_me_patch_updates_profile_but_not_protected_fields():
    client, profile = auth_client(display_name="旧名")
    res = client.patch(
        "/api/auth/me/",
        {"display_name": "新名", "student_verified": True, "role": "admin"},
        format="json",
    )
    assert res.status_code == 200
    profile.refresh_from_db()
    assert profile.display_name == "新名"
    # student_verified / role are read-only via the API.
    assert profile.student_verified is False
    assert profile.role == Profile.Role.STUDENT


def test_grade_out_of_range_rejected():
    client, _ = auth_client()
    res = client.patch("/api/auth/me/", {"grade": 9}, format="json")
    assert res.status_code == 400


# --- Asymmetric signing keys (RS256 via JWKS) --------------------------------
# Supabase's recommended, more secure scheme: tokens are signed with a private
# signing key that never leaves Supabase; the backend verifies with the public
# key fetched from the project JWKS endpoint (cached in-process).

def _rsa_keypair():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _rs256_token(private_key, *, sub=None, expires_in=3600, audience="authenticated"):
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    return jwt.encode(
        {
            "sub": str(sub or uuid.uuid4()),
            "aud": audience,
            "email": "rs256@example.com",
            "role": "authenticated",
            "iat": now,
            "exp": now + datetime.timedelta(seconds=expires_in),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-signing-key"},
    )


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    """Stand-in for PyJWKClient that returns a fixed public key (no network)."""

    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


def test_rs256_token_verified_via_jwks(monkeypatch):
    private_key, public_key = _rsa_keypair()
    monkeypatch.setattr(
        "config.authentication._get_jwks_client",
        lambda: _FakeJWKSClient(public_key),
    )
    sub = uuid.uuid4()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_rs256_token(private_key, sub=sub)}")
    res = client.get("/api/auth/me/")
    assert res.status_code == 200
    assert res.json()["id"] == str(sub)
    assert Profile.objects.filter(id=sub).exists()


def test_rs256_token_signed_with_wrong_key_is_rejected(monkeypatch):
    attacker_key, _ = _rsa_keypair()
    _, legit_public = _rsa_keypair()
    # The server's JWKS returns the *legit* public key, but the token was
    # signed by the attacker's private key -> signature check must fail.
    monkeypatch.setattr(
        "config.authentication._get_jwks_client",
        lambda: _FakeJWKSClient(legit_public),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_rs256_token(attacker_key)}")
    assert client.get("/api/auth/me/").status_code == 401


def test_rs256_token_expired_is_rejected(monkeypatch):
    private_key, public_key = _rsa_keypair()
    monkeypatch.setattr(
        "config.authentication._get_jwks_client",
        lambda: _FakeJWKSClient(public_key),
    )
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {_rs256_token(private_key, expires_in=-60)}"
    )
    assert client.get("/api/auth/me/").status_code == 401


def test_rs256_without_jwks_configured_is_rejected(monkeypatch):
    private_key, _ = _rsa_keypair()
    # No JWKS client available (SUPABASE_URL / SUPABASE_JWKS_URL unset).
    monkeypatch.setattr("config.authentication._get_jwks_client", lambda: None)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_rs256_token(private_key)}")
    assert client.get("/api/auth/me/").status_code == 401
