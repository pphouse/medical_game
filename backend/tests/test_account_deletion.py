"""アカウント削除 (App Store Review Guideline 5.1.1(v))。

「消えた」と言う以上、本当に消えていることをここで担保する。
"""

import uuid

import pytest
from rest_framework.test import APIClient

from accounts.models import DeletedAccount, NotificationPreference, Profile
from quiz.models import AnswerHistory, ReviewSchedule

from .helpers import auth_client, make_question, make_token

pytestmark = pytest.mark.django_db


def _populate(profile):
    """その人の個人データを一通り作る。"""
    question = make_question()
    AnswerHistory.objects.create(
        user=profile, question=question, correct=True, response_time_ms=1000
    )
    ReviewSchedule.objects.create(
        user=profile, question=question, next_review_at="2030-01-01T00:00:00Z"
    )
    NotificationPreference.objects.create(profile=profile)
    return question


def test_deletes_the_profile_and_everything_hanging_off_it():
    client, profile = auth_client(display_name="消える人")
    _populate(profile)

    res = client.delete("/api/auth/me/", {"confirm": True}, format="json")

    assert res.status_code == 204
    assert not Profile.objects.filter(pk=profile.id).exists()
    assert not AnswerHistory.objects.filter(user_id=profile.id).exists()
    assert not ReviewSchedule.objects.filter(user_id=profile.id).exists()
    assert not NotificationPreference.objects.filter(profile_id=profile.id).exists()


def test_keeps_the_questions_they_wrote_but_drops_the_author():
    """他の人が解いている最中の設問を道連れにしない。"""
    client, profile = auth_client()
    question = make_question(creator=profile)
    other, _ = Profile.objects.get_or_create(id=uuid.uuid4())
    AnswerHistory.objects.create(
        user=other, question=question, correct=True, response_time_ms=900
    )

    client.delete("/api/auth/me/", {"confirm": True}, format="json")

    question.refresh_from_db()
    assert question.creator_id is None
    assert AnswerHistory.objects.filter(user_id=other.id, question=question).exists()


def test_confirm_is_required():
    client, profile = auth_client()

    assert client.delete("/api/auth/me/", {}, format="json").status_code == 400
    assert (
        client.delete("/api/auth/me/", {"confirm": "yes"}, format="json").status_code
        == 400
    )
    assert Profile.objects.filter(pk=profile.id).exists()


def test_anonymous_cannot_delete():
    assert APIClient().delete("/api/auth/me/").status_code == 401


def test_the_old_token_cannot_resurrect_the_account():
    """auth.users を消しても JWT は期限まで通る。空の Profile を作らせない。"""
    client, profile = auth_client()
    client.delete("/api/auth/me/", {"confirm": True}, format="json")

    # 別タブから飛んできた1本のつもり（同じトークンを使い続ける）。
    res = client.get("/api/auth/me/")

    assert res.status_code == 401
    assert not Profile.objects.filter(pk=profile.id).exists()
    assert DeletedAccount.objects.filter(pk=profile.id).exists()


def test_the_same_person_can_sign_up_again():
    """再登録時 Supabase は別の UUID を発行するので、墓標は妨げにならない。"""
    client, profile = auth_client()
    client.delete("/api/auth/me/", {"confirm": True}, format="json")

    fresh_id = uuid.uuid4()
    again = APIClient()
    again.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token(fresh_id)}")

    res = again.post("/api/auth/bootstrap/", {"display_name": "再入学"}, format="json")

    assert res.status_code == 200
    assert Profile.objects.filter(pk=fresh_id).exists()


def test_nothing_is_deleted_when_supabase_refuses(settings, monkeypatch):
    """auth.users を消せないのにローカルだけ消すと、ログインできるのに
    データが無いアカウントが残ってしまう。まるごと巻き戻す。"""
    settings.SUPABASE_URL = "https://example.supabase.co"
    settings.SUPABASE_SERVICE_ROLE_KEY = "service-role-key-for-test"

    class Refused:
        status_code = 500

    monkeypatch.setattr("accounts.deletion.requests.delete", lambda *a, **kw: Refused())

    client, profile = auth_client()
    _populate(profile)

    res = client.delete("/api/auth/me/", {"confirm": True}, format="json")

    assert res.status_code == 503
    assert Profile.objects.filter(pk=profile.id).exists()
    assert AnswerHistory.objects.filter(user_id=profile.id).exists()
    assert not DeletedAccount.objects.filter(pk=profile.id).exists()


def test_deletes_the_supabase_auth_user(settings, monkeypatch):
    settings.SUPABASE_URL = "https://example.supabase.co"
    settings.SUPABASE_SERVICE_ROLE_KEY = "service-role-key-for-test"
    called = {}

    class Deleted:
        status_code = 204

    def fake_delete(url, **kwargs):
        called["url"] = url
        called["headers"] = kwargs.get("headers")
        return Deleted()

    monkeypatch.setattr("accounts.deletion.requests.delete", fake_delete)

    client, profile = auth_client()
    res = client.delete("/api/auth/me/", {"confirm": True}, format="json")

    assert res.status_code == 204
    assert called["url"].endswith(f"/auth/v1/admin/users/{profile.id}")
    assert called["headers"]["apikey"] == "service-role-key-for-test"
