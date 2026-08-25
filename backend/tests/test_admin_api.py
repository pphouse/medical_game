"""管理画面API (/api/admin/) のテスト。

学習者向けAPIと違って公開ゲートを外して全 status を扱うため、
権限の穴と一括操作の暴発をここで止める。
"""

import pytest

from accounts.models import Profile
from quiz.models import Question, QuestionReport

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db


def admin_client():
    return auth_client(role=Profile.Role.ADMIN)


class TestAdminPermissions:
    def test_student_cannot_reach_admin_api(self):
        client, _ = auth_client()
        for path in (
            "/api/admin/stats/",
            "/api/admin/questions/",
            "/api/admin/reports/",
            "/api/admin/users/",
        ):
            assert client.get(path).status_code == 403, path

    def test_moderator_can_manage_questions_but_not_roles(self):
        client, _ = auth_client(role=Profile.Role.MODERATOR)
        assert client.get("/api/admin/questions/").status_code == 200
        # ロール変更は権限昇格になるので moderator には許さない
        assert client.get("/api/admin/users/").status_code == 403

    def test_admin_can_reach_everything(self):
        client, _ = admin_client()
        for path in (
            "/api/admin/stats/",
            "/api/admin/questions/",
            "/api/admin/reports/",
            "/api/admin/users/",
        ):
            assert client.get(path).status_code == 200, path


class TestAdminQuestionList:
    def test_lists_every_status_unlike_learner_api(self):
        client, _ = admin_client()
        make_question(question_text="公開済み")
        make_question(question_text="審査待ち", status="pending")
        make_question(question_text="却下済み", status="rejected")

        rows = client.get("/api/admin/questions/").json()["results"]
        assert {r["question_text"] for r in rows} == {"公開済み", "審査待ち", "却下済み"}

    def test_filters(self):
        client, _ = admin_client()
        make_question(question_text="CBTの問題", exam_type="CBT", category="循環器")
        make_question(
            question_text="国試の問題", exam_type="KOKUSHI", category="呼吸器", status="pending"
        )

        by_exam = client.get("/api/admin/questions/?exam_type=KOKUSHI").json()["results"]
        assert [r["question_text"] for r in by_exam] == ["国試の問題"]

        by_status = client.get("/api/admin/questions/?status=pending").json()["results"]
        assert [r["question_text"] for r in by_status] == ["国試の問題"]

        by_category = client.get("/api/admin/questions/?category=循環器").json()["results"]
        assert [r["question_text"] for r in by_category] == ["CBTの問題"]

    def test_keyword_search_matches_body_and_explanation(self):
        client, _ = admin_client()
        make_question(question_text="心房細動の治療", explanation="解説")
        make_question(question_text="別の設問", explanation="心房細動について")
        make_question(question_text="無関係な設問", explanation="無関係")

        rows = client.get("/api/admin/questions/?q=心房細動").json()["results"]
        assert {r["question_text"] for r in rows} == {"心房細動の治療", "別の設問"}

    def test_report_count_is_exposed(self):
        client, admin = admin_client()
        question = make_question()
        QuestionReport.objects.create(question=question, reporter=admin, reason="wrong_answer")

        rows = client.get("/api/admin/questions/").json()["results"]
        assert rows[0]["report_count"] == 1


class TestAdminQuestionWrite:
    payload = {
        "category": "循環器",
        "exam_type": "CBT",
        "difficulty": 2,
        "question_text": "管理者が作った設問",
        "choices": [{"key": k, "text": f"選択肢{k}"} for k in "ABCDE"],
        "correct_choice_key": "C",
        "explanation": "解説",
        "status": "published",
    }

    def test_admin_can_create_published_question(self):
        client, _ = admin_client()
        res = client.post("/api/admin/questions/", self.payload, format="json")
        assert res.status_code == 201, res.json()
        question = Question.objects.get(question_text="管理者が作った設問")
        assert question.status == Question.Status.PUBLISHED
        # 管理者が直接書いたものは official 扱い（LLM生成の集計と混ざらないように）
        assert question.source == Question.Source.OFFICIAL
        assert question.reviewed_at is not None

    def test_create_rejects_bad_choices(self):
        client, _ = admin_client()
        bad = {**self.payload, "choices": [{"key": "A", "text": "1つだけ"}]}
        assert client.post("/api/admin/questions/", bad, format="json").status_code == 400

    def test_create_rejects_answer_key_not_in_choices(self):
        client, _ = admin_client()
        bad = {**self.payload, "correct_choice_key": "E", "choices": [
            {"key": k, "text": f"選択肢{k}"} for k in "ABCD"
        ]}
        assert client.post("/api/admin/questions/", bad, format="json").status_code == 400

    def test_admin_can_edit_a_question_with_answer_history(self):
        # 学習者向けAPIは履歴のある問題の本文編集を禁止するが、
        # 管理側は誤りの訂正が目的なので通す。
        client, _ = admin_client()
        question = make_question(answer_count=42)
        res = client.patch(
            f"/api/admin/questions/{question.id}/",
            {"question_text": "訂正後の設問"},
            format="json",
        )
        assert res.status_code == 200
        question.refresh_from_db()
        assert question.question_text == "訂正後の設問"
        assert res.json()["answer_count"] == 42  # 画面で警告を出せるように返す

    def test_status_change_records_reviewer(self):
        client, admin = admin_client()
        question = make_question(status="pending")
        client.patch(
            f"/api/admin/questions/{question.id}/", {"status": "published"}, format="json"
        )
        question.refresh_from_db()
        assert question.status == Question.Status.PUBLISHED
        assert question.reviewed_by == admin
        assert question.reviewed_at is not None

    def test_delete(self):
        client, _ = admin_client()
        question = make_question()
        assert client.delete(f"/api/admin/questions/{question.id}/").status_code == 204
        assert not Question.objects.filter(pk=question.id).exists()


class TestAdminBulkStatus:
    def test_bulk_by_ids(self):
        client, _ = admin_client()
        ids = [make_question(question_text=f"設問{i}", status="pending").id for i in range(3)]
        res = client.post(
            "/api/admin/questions/bulk-status/",
            {"ids": ids, "status": "published"},
            format="json",
        )
        assert res.status_code == 200
        assert res.json()["updated"] == 3
        assert Question.objects.filter(status="published").count() == 3

    def test_bulk_by_filter_requires_matching_expected_count(self):
        client, _ = admin_client()
        for i in range(3):
            make_question(question_text=f"設問{i}", status="pending")

        # 件数が食い違うと拒否する（絞り込みの取り違えで全問公開する事故を防ぐ）
        mismatch = client.post(
            "/api/admin/questions/bulk-status/",
            {"filters": {"status": "pending"}, "expected_count": 99, "status": "published"},
            format="json",
        )
        assert mismatch.status_code == 400
        assert Question.objects.filter(status="published").count() == 0

        ok = client.post(
            "/api/admin/questions/bulk-status/",
            {"filters": {"status": "pending"}, "expected_count": 3, "status": "published"},
            format="json",
        )
        assert ok.status_code == 200
        assert Question.objects.filter(status="published").count() == 3

    def test_bulk_rejects_unknown_status(self):
        client, _ = admin_client()
        res = client.post(
            "/api/admin/questions/bulk-status/",
            {"ids": [1], "status": "とりけし"},
            format="json",
        )
        assert res.status_code == 400


class TestAdminUsers:
    def test_admin_can_change_roles(self):
        client, _ = admin_client()
        _, target = auth_client()
        res = client.patch(
            "/api/admin/users/", {"id": str(target.id), "role": "moderator"}, format="json"
        )
        assert res.status_code == 200
        target.refresh_from_db()
        assert target.role == Profile.Role.MODERATOR

    def test_admin_cannot_demote_themselves(self):
        # 最後の管理者が自分を降格させると誰も管理できなくなる
        client, admin = admin_client()
        res = client.patch(
            "/api/admin/users/", {"id": str(admin.id), "role": "student"}, format="json"
        )
        assert res.status_code == 400
        admin.refresh_from_db()
        assert admin.role == Profile.Role.ADMIN


class TestAdminStats:
    def test_stats_break_down_by_status_and_exam_type(self):
        client, _ = admin_client()
        make_question(exam_type="CBT")
        make_question(exam_type="KOKUSHI", status="pending")
        make_question(exam_type="KOKUSHI", status="pending", question_text="もう1問")

        body = client.get("/api/admin/stats/").json()
        assert body["total"] == 3
        assert body["by_status"] == {"published": 1, "pending": 2}
        assert body["by_exam_type"] == {"CBT": 1, "KOKUSHI": 2}
        # カテゴリは exam_type ごとに分けて数える。同じ「循環器」でも CBT と
        # 国試では別の分野として運用するため、混ぜると内訳が読めない。
        rows = {(c["category"], c["exam_type"]): c["total"] for c in body["categories"]}
        assert rows == {("循環器", "CBT"): 1, ("循環器", "KOKUSHI"): 2}


class TestSetRoleCommand:
    """最初の管理者を作るための管理コマンド。

    ロール変更APIは IsAdmin で守っているので、管理者が1人もいない状態では
    誰も昇格させられない。その鶏と卵をこのコマンドで解く。
    """

    def test_promotes_by_display_name(self):
        from django.core.management import call_command

        _, profile = auth_client()
        profile.display_name = "なおと"
        profile.save(update_fields=["display_name"])

        call_command("set_role", "--display-name", "なおと", "--role", "admin")
        profile.refresh_from_db()
        assert profile.role == Profile.Role.ADMIN

    def test_refuses_ambiguous_match(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        for _ in range(2):
            _, p = auth_client()
            p.display_name = "同名"
            p.save(update_fields=["display_name"])

        with pytest.raises(CommandError, match="2件が該当"):
            call_command("set_role", "--display-name", "同名", "--role", "admin")

    def test_refuses_unknown_user(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match="該当する利用者がいません"):
            call_command("set_role", "--display-name", "いない人", "--role", "admin")


class TestAdminCategoryGate:
    """管理APIが正規の分野名以外を書き込ませないこと。

    category は自由入力の CharField で統制が無く、「循環器」と「循環器系」の
    ように同じ分野が別名で並存していた。画面はプルダウンで選ばせるが、
    API を直に叩かれても入らないようにする。
    """

    payload = {
        "exam_type": "CBT",
        "difficulty": 2,
        "question_text": "分野ゲートの確認用の設問",
        "choices": [{"key": k, "text": f"選択肢{k}"} for k in "ABCDE"],
        "correct_choice_key": "A",
        "explanation": "解説",
        "status": "pending",
    }

    def test_canonical_category_is_accepted(self):
        client, _ = admin_client()
        res = client.post(
            "/api/admin/questions/", {**self.payload, "category": "循環器"}, format="json"
        )
        assert res.status_code == 201, res.json()

    def test_legacy_name_is_rejected_with_the_correct_one(self):
        client, _ = admin_client()
        res = client.post(
            "/api/admin/questions/", {**self.payload, "category": "循環器系"}, format="json"
        )
        assert res.status_code == 400
        assert "循環器" in str(res.json()["category"])

    def test_unknown_category_is_rejected(self):
        client, _ = admin_client()
        res = client.post(
            "/api/admin/questions/", {**self.payload, "category": "でたらめ分野"}, format="json"
        )
        assert res.status_code == 400

    def test_stats_exposes_the_canon_for_the_dropdown(self):
        from quiz.categories import CANONICAL_CATEGORIES

        client, _ = admin_client()
        body = client.get("/api/admin/stats/").json()
        assert body["canonical_categories"] == list(CANONICAL_CATEGORIES)
