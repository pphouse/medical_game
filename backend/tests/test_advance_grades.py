import uuid

import pytest

from accounts.models import Profile

pytestmark = pytest.mark.django_db


class TestAdvanceGradesCommand:
    def test_increments_grade_except_final_year_and_unset(self):
        p1 = Profile.objects.create(id=uuid.uuid4(), grade=4)
        p2 = Profile.objects.create(id=uuid.uuid4(), grade=6)
        p3 = Profile.objects.create(id=uuid.uuid4(), grade=None)

        from django.core.management import call_command

        call_command("advance_grades")

        p1.refresh_from_db()
        p2.refresh_from_db()
        p3.refresh_from_db()
        assert p1.grade == 5
        assert p2.grade == 6  # 最終学年は据え置き
        assert p3.grade is None  # 未設定は対象外


class TestAdvanceGradesInternalEndpoint:
    def test_rejects_bad_token(self, client):
        res = client.post(
            "/api/internal/advance-grades/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": "wrong"},
        )
        assert res.status_code in (401, 403)

    def test_advances_with_valid_token(self, client, settings):
        profile = Profile.objects.create(id=uuid.uuid4(), grade=4)
        res = client.post(
            "/api/internal/advance-grades/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        assert res.status_code == 200
        assert res.json()["updated"] == 1
        profile.refresh_from_db()
        assert profile.grade == 5
