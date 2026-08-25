import uuid

import pytest

from accounts.models import Profile
from tests.helpers import auth_client


@pytest.mark.django_db
class TestResolvedExamType:
    """未選択なら学年から、選択済みならその値。学年の繰り上げに追従するのは
    未選択のときだけ、という取り決めを固定する。"""

    @pytest.mark.parametrize(
        "grade,expected",
        [(1, "CBT"), (4, "CBT"), (5, "KOKUSHI"), (6, "KOKUSHI")],
    )
    def test_falls_back_to_grade(self, grade, expected):
        profile = Profile(id=uuid.uuid4(), grade=grade, exam_preference="")
        assert profile.resolved_exam_type == expected

    def test_unset_grade_falls_back_to_cbt(self):
        profile = Profile(id=uuid.uuid4(), grade=None, exam_preference="")
        assert profile.resolved_exam_type == "CBT"

    @pytest.mark.parametrize("grade", [1, 4, 5, 6, None])
    def test_explicit_choice_wins_over_grade(self, grade):
        """4年生が国試を選ぶ、6年生がCBTを選ぶ、どちらも尊重する。"""
        profile = Profile(id=uuid.uuid4(), grade=grade, exam_preference="KOKUSHI")
        assert profile.resolved_exam_type == "KOKUSHI"
        profile.exam_preference = "CBT"
        assert profile.resolved_exam_type == "CBT"

    def test_explicit_choice_survives_grade_advance(self):
        """4月1日の繰り上げで学年が変わっても、選んだ設定は動かない。"""
        profile = Profile(id=uuid.uuid4(), grade=4, exam_preference="CBT")
        profile.grade = 5
        assert profile.resolved_exam_type == "CBT"


@pytest.mark.django_db
class TestExamPreferenceApi:
    def test_me_exposes_preference_and_resolved_value(self):
        client, profile = auth_client(grade=4)
        body = client.get("/api/auth/me/").json()
        assert body["exam_preference"] == ""
        assert body["resolved_exam_type"] == "CBT"

    def test_patch_updates_preference(self):
        client, profile = auth_client(grade=4)
        res = client.patch(
            "/api/auth/me/", {"exam_preference": "KOKUSHI"}, format="json"
        )
        assert res.status_code == 200
        assert res.json()["resolved_exam_type"] == "KOKUSHI"
        profile.refresh_from_db()
        assert profile.exam_preference == "KOKUSHI"

    def test_patch_back_to_auto(self):
        client, profile = auth_client(grade=5, exam_preference="CBT")
        res = client.patch("/api/auth/me/", {"exam_preference": ""}, format="json")
        assert res.status_code == 200
        # 未選択に戻せば、また学年（5年生）から決まる。
        assert res.json()["resolved_exam_type"] == "KOKUSHI"

    def test_rejects_unknown_value(self):
        client, _ = auth_client(grade=4)
        res = client.patch("/api/auth/me/", {"exam_preference": "OSCE"}, format="json")
        assert res.status_code == 400

    def test_resolved_exam_type_is_read_only(self):
        """実効値はサーバが決める。クライアントから直接は書けない。"""
        client, profile = auth_client(grade=4)
        client.patch(
            "/api/auth/me/", {"resolved_exam_type": "KOKUSHI"}, format="json"
        )
        profile.refresh_from_db()
        assert profile.exam_preference == ""
        assert profile.resolved_exam_type == "CBT"
