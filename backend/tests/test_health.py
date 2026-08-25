import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestHealthEndpoint:
    def test_returns_ok_without_authentication(self):
        """認証不要であること。ここが 401 だと疎通確認の役に立たない。"""
        res = APIClient().get("/api/health/")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_does_not_leak_configuration(self):
        """設定値を返さないこと。本番の構成を晒さないための約束。"""
        body = APIClient().get("/api/health/").json()
        assert set(body) == {"status"}

    def test_rejects_disallowed_host(self, settings):
        """ALLOWED_HOSTS 未設定の本番で 400 になることを保証する。
        この 400 こそが「バックエンドまでは届いている」ことの手掛かりになる。"""
        settings.ALLOWED_HOSTS = ["example.com"]
        res = APIClient().get("/api/health/", headers={"host": "wrong.vercel.app"})
        assert res.status_code == 400
