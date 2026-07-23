import uuid

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
