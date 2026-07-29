import pytest

from accounts.models import Profile, StudentVerification, University
from quiz.models import Question

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db

QUESTION_PAYLOAD = {
    "category": "循環器",
    "topic": "心不全",
    "exam_type": "CBT",
    "difficulty": 2,
    "question_text": "ユーザー作成のテスト設問です。最も適切なのはどれか。",
    "choices": [{"key": k, "text": f"選択肢{k}"} for k in "ABCDE"],
    "correct_choice_key": "B",
    "explanation": "テスト解説",
    "visibility": "public",
}


def verified_client(university=None, **kwargs):
    client, profile = auth_client(
        student_verified=True, university=university, **kwargs
    )
    return client, profile


class TestUniversityOnlyVisibility:
    """完了条件: A大学の university_only 問題が B大学ユーザーの API レスポンス
    に現れない (spec フェーズ7)."""

    def setup_method(self):
        self.univ_a = University.objects.create(name="A大学")
        self.univ_b = University.objects.create(name="B大学")
        self.question = make_question(
            question_text="A大学限定の設問",
            visibility=Question.Visibility.UNIVERSITY_ONLY,
            university=self.univ_a,
        )
        make_question(question_text="全体公開の設問")

    def list_texts(self, client):
        res = client.get("/api/quiz/questions/?category=循環器")
        return [q["question_text"] for q in res.json()["results"]]

    def test_visible_to_verified_same_university(self):
        client, _ = verified_client(university=self.univ_a)
        assert "A大学限定の設問" in self.list_texts(client)

    def test_hidden_from_other_university(self):
        client, _ = verified_client(university=self.univ_b)
        texts = self.list_texts(client)
        assert "A大学限定の設問" not in texts
        assert "全体公開の設問" in texts

    def test_hidden_from_unverified_same_university(self):
        client, _ = auth_client(student_verified=False, university=self.univ_a)
        assert "A大学限定の設問" not in self.list_texts(client)

    def test_cannot_answer_invisible_question(self):
        client, _ = verified_client(university=self.univ_b)
        res = client.post(
            "/api/quiz/answers/",
            {
                "question_id": self.question.id,
                "selected_choice_key": "A",
                "response_time_ms": 100,
            },
            format="json",
        )
        assert res.status_code == 404


class TestQuestionCreation:
    def test_unverified_cannot_create(self):
        client, _ = auth_client(student_verified=False)
        res = client.post("/api/quiz/questions/", QUESTION_PAYLOAD, format="json")
        assert res.status_code == 403
        assert "学生証認証" in res.content.decode()

    def test_create_draft_then_submit_then_approve(self):
        client, profile = verified_client()
        res = client.post("/api/quiz/questions/", QUESTION_PAYLOAD, format="json")
        assert res.status_code == 201
        body = res.json()
        assert body["status"] == "draft"
        question = Question.objects.get(pk=body["id"])
        assert question.creator == profile
        assert question.source == Question.Source.USER

        # draft は演習一覧に出ない
        assert client.get("/api/quiz/questions/?category=循環器").json()["results"] == []

        assert (
            client.post(f"/api/quiz/questions/{question.id}/submit/").json()["status"]
            == "pending"
        )

        mod, _ = auth_client(role=Profile.Role.MODERATOR)
        mod.post(f"/api/quiz/review/questions/{question.id}/approve/")
        question.refresh_from_db()
        assert question.status == Question.Status.PUBLISHED

    def test_university_only_forces_creator_university(self):
        univ_a = University.objects.create(name="A大学")
        univ_b = University.objects.create(name="B大学")
        client, _ = verified_client(university=univ_a)
        payload = {
            **QUESTION_PAYLOAD,
            "visibility": "university_only",
            "university": univ_b.id,  # クライアント指定は無視される
        }
        res = client.post("/api/quiz/questions/", payload, format="json")
        assert res.status_code == 201
        question = Question.objects.get(pk=res.json()["id"])
        assert question.university == univ_a

    def test_choices_validation(self):
        client, _ = verified_client()
        bad = {**QUESTION_PAYLOAD, "choices": QUESTION_PAYLOAD["choices"][:4]}
        assert client.post("/api/quiz/questions/", bad, format="json").status_code == 400
        bad = {**QUESTION_PAYLOAD, "correct_choice_key": "F"}
        assert client.post("/api/quiz/questions/", bad, format="json").status_code == 400


class TestQuestionEditing:
    def test_only_owner_or_moderator(self):
        owner, _ = verified_client()
        question_id = owner.post(
            "/api/quiz/questions/", QUESTION_PAYLOAD, format="json"
        ).json()["id"]

        other, _ = verified_client()
        assert (
            other.patch(
                f"/api/quiz/questions/{question_id}/", {"explanation": "x"}, format="json"
            ).status_code
            == 403
        )
        mod, _ = auth_client(role=Profile.Role.MODERATOR)
        assert (
            mod.patch(
                f"/api/quiz/questions/{question_id}/",
                {"explanation": "モデレーター追記"},
                format="json",
            ).status_code
            == 200
        )

    def test_answered_question_allows_explanation_only(self):
        owner, _ = verified_client()
        question_id = owner.post(
            "/api/quiz/questions/", QUESTION_PAYLOAD, format="json"
        ).json()["id"]
        Question.objects.filter(pk=question_id).update(answer_count=3)

        res = owner.patch(
            f"/api/quiz/questions/{question_id}/",
            {"question_text": "書き換え"},
            format="json",
        )
        assert res.status_code == 400
        assert "解説の追記のみ" in res.content.decode()

        res = owner.patch(
            f"/api/quiz/questions/{question_id}/",
            {"explanation": "解説を追記しました"},
            format="json",
        )
        assert res.status_code == 200

    def test_owner_delete_blocked_after_answers(self):
        owner, _ = verified_client()
        question_id = owner.post(
            "/api/quiz/questions/", QUESTION_PAYLOAD, format="json"
        ).json()["id"]
        Question.objects.filter(pk=question_id).update(answer_count=1)
        assert owner.delete(f"/api/quiz/questions/{question_id}/").status_code == 400

        mod, _ = auth_client(role=Profile.Role.MODERATOR)
        assert mod.delete(f"/api/quiz/questions/{question_id}/").status_code == 204


class TestReports:
    def test_three_reports_auto_unpublish(self):
        question = make_question(question_text="通報される設問")
        reporters = [auth_client()[0] for _ in range(3)]

        for i, client in enumerate(reporters):
            res = client.post(
                f"/api/quiz/questions/{question.id}/report/",
                {"reason": "wrong_answer", "detail": f"通報{i}"},
                format="json",
            )
            assert res.status_code == 201

        question.refresh_from_db()
        assert question.status == Question.Status.PENDING  # 出題から外れる

    def test_duplicate_report_rejected(self):
        question = make_question()
        client, _ = auth_client()
        client.post(
            f"/api/quiz/questions/{question.id}/report/",
            {"reason": "typo"},
            format="json",
        )
        res = client.post(
            f"/api/quiz/questions/{question.id}/report/",
            {"reason": "typo"},
            format="json",
        )
        assert res.status_code == 400


class TestStudentVerificationFlow:
    def test_apply_complete_approve(self, monkeypatch):
        monkeypatch.setattr(
            "accounts.views.create_signed_upload_url",
            lambda path: {"path": path, "token": "t", "signed_url": "https://x/y", "bucket": "student-ids"},
        )
        university = University.objects.create(name="申請大学")
        client, profile = auth_client()

        res = client.post(
            "/api/auth/student-verification/", {"university_id": university.id}, format="json"
        )
        assert res.status_code == 201
        body = res.json()
        assert body["upload"]["token"] == "t"
        verification_id = body["verification"]["id"]
        assert str(profile.id) in StudentVerification.objects.get().image_path

        assert (
            client.patch(
                f"/api/auth/student-verification/{verification_id}/complete/"
            ).json()["status"]
            == "pending"
        )

        # 審査待ち中の再申請は不可
        assert (
            client.post(
                "/api/auth/student-verification/",
                {"university_id": university.id},
                format="json",
            ).status_code
            == 400
        )

        mod, moderator = auth_client(role=Profile.Role.MODERATOR)
        res = mod.post(f"/api/auth/student-verification/{verification_id}/approve/")
        assert res.status_code == 200
        profile.refresh_from_db()
        assert profile.student_verified is True
        assert profile.university == university
        verification = StudentVerification.objects.get()
        assert verification.reviewed_by == moderator

    def test_reject_deletes_image(self, monkeypatch):
        monkeypatch.setattr(
            "accounts.views.create_signed_upload_url",
            lambda path: {"path": path, "token": "t", "signed_url": None, "bucket": "b"},
        )
        deleted = []
        monkeypatch.setattr(
            "accounts.storage.delete_student_id_image",
            lambda path: deleted.append(path) or True,
        )
        university = University.objects.create(name="却下大学")
        client, profile = auth_client()
        verification_id = client.post(
            "/api/auth/student-verification/", {"university_id": university.id}, format="json"
        ).json()["verification"]["id"]
        client.patch(f"/api/auth/student-verification/{verification_id}/complete/")

        mod, _ = auth_client(role=Profile.Role.MODERATOR)
        mod.post(
            f"/api/auth/student-verification/{verification_id}/reject/",
            {"reason": "写真が不鮮明です"},
            format="json",
        )
        verification = StudentVerification.objects.get()
        assert verification.status == "rejected"
        assert verification.image_deleted_at is not None  # 却下→即削除 (spec)
        assert deleted == [verification.image_path]
        profile.refresh_from_db()
        assert profile.student_verified is False

    def test_stale_draft_discarded_on_reapply(self, monkeypatch):
        """アップロード未完了の draft が残っても再申請できる（ソフトロック防止）."""
        monkeypatch.setattr(
            "accounts.views.create_signed_upload_url",
            lambda path: {"path": path, "token": "t", "signed_url": None, "bucket": "b"},
        )
        deleted = []
        monkeypatch.setattr(
            "accounts.views.delete_student_id_image",
            lambda path: deleted.append(path) or True,
        )
        university = University.objects.create(name="再申請大学")
        client, _ = auth_client()

        first = client.post(
            "/api/auth/student-verification/", {"university_id": university.id}, format="json"
        )
        assert first.status_code == 201
        stale_path = StudentVerification.objects.get().image_path

        # complete を呼ばずに（アップロード失敗を想定）もう一度申請
        second = client.post(
            "/api/auth/student-verification/", {"university_id": university.id}, format="json"
        )
        assert second.status_code == 201
        assert StudentVerification.objects.count() == 1
        assert deleted == [stale_path]

    def test_student_cannot_use_moderator_endpoints(self):
        client, _ = auth_client()
        assert client.get("/api/auth/student-verification/pending/").status_code == 403
