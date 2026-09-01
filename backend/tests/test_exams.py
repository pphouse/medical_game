import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import University
from accounts.ranktier import STARTING_POINTS
from exams.models import MockAnswer, MockExam, MockQuestion, MockResult
from quiz.models import AnswerHistory

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db


def make_exam(n_questions=4, *, opens_in=-1, closes_in=60, duration=120, **kwargs):
    now = timezone.now()
    exam = MockExam.objects.create(
        title="テスト模試",
        start_at=now + datetime.timedelta(minutes=opens_in),
        end_at=now + datetime.timedelta(minutes=closes_in),
        question_count=n_questions,
        duration_minutes=duration,
        **kwargs,
    )
    for i in range(n_questions):
        question = make_question(
            question_text=f"模試設問{i}",
            correct_choice_key="A",
            blueprint_code="D-5-4)-(1)-①" if i % 2 == 0 else "D-7-4)-(3)-①",
        )
        MockQuestion.objects.create(mock_exam=exam, question=question, order=i + 1)
    return exam


def start_and_answer_all(client, exam, key="A"):
    client.post(f"/api/exams/{exam.id}/start/")
    questions = client.get(f"/api/exams/{exam.id}/questions/").json()["questions"]
    for q in questions:
        client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": q["id"], "selected_choice_key": key, "response_time_ms": 1000},
            format="json",
        )
    client.post(f"/api/exams/{exam.id}/submit/")


class TestExamFlow:
    def test_start_only_within_window(self):
        client, _ = auth_client()
        not_open = make_exam(opens_in=30)  # 30分後開始
        assert client.post(f"/api/exams/{not_open.id}/start/").status_code == 400
        closed = make_exam(opens_in=-120, closes_in=-30)
        assert client.post(f"/api/exams/{closed.id}/start/").status_code == 400

    def test_double_start_rejected(self):
        client, _ = auth_client()
        exam = make_exam()
        assert client.post(f"/api/exams/{exam.id}/start/").status_code == 201
        res = client.post(f"/api/exams/{exam.id}/start/")
        assert res.status_code == 400
        assert "二重受験" in res.content.decode()

    def test_grade_filter(self):
        client, _ = auth_client(grade=2)
        exam = make_exam(target_grade_min=4, target_grade_max=6)
        assert client.post(f"/api/exams/{exam.id}/start/").status_code == 400
        assert client.get("/api/exams/").json() == []

    def test_questions_hide_answers(self):
        client, _ = auth_client()
        exam = make_exam()
        client.post(f"/api/exams/{exam.id}/start/")
        body = client.get(f"/api/exams/{exam.id}/questions/").json()
        assert len(body["questions"]) == 4
        text = str(body)
        assert "correct_choice_key" not in text
        assert "explanation" not in text

    def test_questions_include_exam_kind_for_block_display(self):
        """CBT模試のブロック表示（フロント側）に使う。"""
        client, _ = auth_client(grade=4)
        exam = make_exam(kind=MockExam.Kind.CBT_ONCE, exam_type="CBT")
        client.post(f"/api/exams/{exam.id}/start/")
        body = client.get(f"/api/exams/{exam.id}/questions/").json()
        assert body["kind"] == "cbt_once"

    def test_answers_rejected_after_time_limit(self):
        client, profile = auth_client()
        exam = make_exam(duration=1, closes_in=600)
        client.post(f"/api/exams/{exam.id}/start/")
        question_id = exam.mock_questions.first().question_id

        # 制限時間内は保存できる
        ok = client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "A"},
            format="json",
        )
        assert ok.status_code == 200

        # started_at を2分前に偽装 → duration 1分を超過
        MockResult.objects.filter(user=profile, mock_exam=exam).update(
            started_at=timezone.now() - datetime.timedelta(minutes=2)
        )
        res = client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "B"},
            format="json",
        )
        assert res.status_code == 400
        assert "制限時間" in res.content.decode()

    def test_answers_rejected_after_submit(self):
        client, _ = auth_client()
        exam = make_exam()
        client.post(f"/api/exams/{exam.id}/start/")
        question_id = exam.mock_questions.first().question_id
        client.post(f"/api/exams/{exam.id}/submit/")
        res = client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "A"},
            format="json",
        )
        assert res.status_code == 400
        assert "提出済み" in res.content.decode()

    def test_answer_upsert_no_grading_leak(self):
        client, _ = auth_client()
        exam = make_exam()
        client.post(f"/api/exams/{exam.id}/start/")
        question_id = exam.mock_questions.first().question_id
        res = client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "B"},
            format="json",
        )
        assert "correct" not in res.json()
        client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "A"},
            format="json",
        )
        assert MockAnswer.objects.count() == 1  # upsert
        assert MockAnswer.objects.get().selected_choice_key == "A"


class TestGrading:
    def test_full_cycle_grades_ranks_and_sections(self):
        university = University.objects.create(name="採点大学")
        c1, p1 = auth_client(display_name="満点", university=university)
        c2, p2 = auth_client(display_name="半分", university=university)
        c3, _p3 = auth_client(display_name="よそ者")
        exam = make_exam(n_questions=4)

        start_and_answer_all(c1, exam, key="A")  # 4/4
        # c2: 半分正解
        c2.post(f"/api/exams/{exam.id}/start/")
        for i, mq in enumerate(exam.mock_questions.all()):
            c2.post(
                f"/api/exams/{exam.id}/answers/",
                {
                    "question_id": mq.question_id,
                    "selected_choice_key": "A" if i < 2 else "B",
                },
                format="json",
            )
        c2.post(f"/api/exams/{exam.id}/submit/")
        start_and_answer_all(c3, exam, key="B")  # 0/4

        # 採点前は「採点中」
        assert c1.get(f"/api/exams/{exam.id}/result/").json()["status"] == "grading"

        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")

        r1 = MockResult.objects.get(user=p1)
        r2 = MockResult.objects.get(user=p2)
        assert (r1.score, r1.rank, r1.university_rank) == (4, 1, 1)
        assert (r2.score, r2.rank, r2.university_rank) == (2, 2, 2)
        assert r1.deviation_score > 50 > MockResult.objects.get(user__display_name="よそ者").deviation_score
        assert r1.percentile == pytest.approx(66.7, abs=0.1)
        assert r1.section_scores == {"D-5": 1.0, "D-7": 1.0}
        # c2 は order 1,2 のみ正解 = D-5/D-7 に1問ずつ → 各 0.5
        assert r2.section_scores == {"D-5": 0.5, "D-7": 0.5}

        # AnswerHistory へ context=mock で複写・習熟度は未演習のまま (spec)
        copied = AnswerHistory.objects.filter(user=p2, context="mock")
        assert copied.count() == 4
        assert set(copied.values_list("mastery_level", flat=True)) == {"unstudied"}

        body = c1.get(f"/api/exams/{exam.id}/result/").json()
        assert body["status"] == "graded"
        assert body["rank"] == 1
        assert body["deviation_score"] == r1.deviation_score
        assert len(body["review"]) == 4
        assert body["review"][0]["correct_choice_key"] == "A"

    def test_grading_is_idempotent_for_history_copy(self):
        client, profile = auth_client()
        client2, _ = auth_client()
        exam = make_exam(n_questions=2)
        start_and_answer_all(client, exam)
        start_and_answer_all(client2, exam)
        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")
        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")
        assert AnswerHistory.objects.filter(user=profile, context="mock").count() == 2


class TestScheduledExamCommand:
    def test_creates_exam_with_proportional_questions(self):
        for i in range(6):
            make_question(question_text=f"循{i}", category="循環器", blueprint_code="D-5-1)-①")
        for i in range(6):
            make_question(question_text=f"消{i}", category="消化器", blueprint_code="D-7-1)-①")
        call_command("create_scheduled_exam", "--kind", "cbt_once", "--open-now", "--count", "8")
        exam = MockExam.objects.get()
        assert exam.mock_questions.count() == 8
        areas = {
            mq.question.blueprint_code[:3] for mq in exam.mock_questions.all()
        }
        assert areas == {"D-5", "D-7"}
        assert exam.effective_status() == MockExam.Status.OPEN


class TestInternalCreateExamsEndpoint:
    """Vercel Cron / pg_cron から叩く模試の自動生成トリガ。"""

    def test_rejects_bad_token(self, client):
        res = client.post(
            "/api/internal/create-exams/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": "wrong"},
        )
        assert res.status_code in (401, 403)

    def test_valid_token_creates_scheduled_exams(self, client, settings):
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(5):
                make_question(
                    question_text=f"{exam_type}内部設問{i}", correct_choice_key="A", exam_type=exam_type
                )
        res = client.post(
            "/api/internal/create-exams/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        assert res.status_code == 200
        assert MockExam.objects.filter(kind=MockExam.Kind.MONTHLY).count() == 2

    def test_vercel_cron_get_with_bearer_secret_works(self, client, settings):
        settings.CRON_SECRET = "test-cron-secret"
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(5):
                make_question(
                    question_text=f"{exam_type}-cron設問{i}", correct_choice_key="A", exam_type=exam_type
                )
        res = client.get(
            "/api/internal/create-exams/",
            headers={"Authorization": "Bearer test-cron-secret"},
        )
        assert res.status_code == 200

    def test_one_exam_types_empty_pool_does_not_block_the_others(self, client, settings):
        """KOKUSHI の問題プールが尽きていても、CBTのmonthly/cbt_onceは作られる。"""
        for i in range(5):
            make_question(question_text=f"CBT単独設問{i}", correct_choice_key="A", exam_type="CBT")
        res = client.post(
            "/api/internal/create-exams/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        assert res.status_code == 200
        body = res.json()
        assert "error" in body["created"]["large"]  # KOKUSHIの問題が無い
        assert MockExam.objects.filter(kind=MockExam.Kind.CBT_ONCE, exam_type="CBT").exists()
        assert MockExam.objects.filter(kind=MockExam.Kind.MONTHLY, exam_type="CBT").exists()


class TestScheduledExamIdempotency:
    """Vercel Cron から毎日叩いても、同じ日付分は重複作成しない。"""

    def test_calling_monthly_twice_the_same_day_creates_only_one_pair(self):
        # --open-now/--start は明示的な上書きとして冪等性チェックを飛ばす
        # （デモ用）ので、ここでは実際の Cron 呼び出しと同じ「無指定」で叩く。
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(10):
                make_question(
                    question_text=f"{exam_type}冪等設問{i}", correct_choice_key="A", exam_type=exam_type
                )
        call_command("create_scheduled_exam", "--kind", "monthly")
        call_command("create_scheduled_exam", "--kind", "monthly")
        assert MockExam.objects.filter(kind=MockExam.Kind.MONTHLY).count() == 2


class TestCbtOnceDefaults:
    """CBT模試（生涯1回）の既定値: 実際のCBTに合わせて4年生のみ・320問構成。"""

    def test_default_targets_grade_4_only(self):
        for i in range(5):
            make_question(question_text=f"CBT既定設問{i}", correct_choice_key="A", exam_type="CBT")
        call_command("create_scheduled_exam", "--kind", "cbt_once", "--open-now")
        exam = MockExam.objects.get(kind=MockExam.Kind.CBT_ONCE)
        assert exam.target_grade_min == 4
        assert exam.target_grade_max == 4


class TestCbtOnceExam:
    """CBT模試（生涯1回）: 提出と同時に個別採点され、二度目は受験できない。"""

    def test_immediate_grading_and_single_attempt(self):
        client, profile = auth_client(grade=3)
        exam = make_exam(n_questions=4, kind=MockExam.Kind.CBT_ONCE, exam_type="CBT")
        start_and_answer_all(client, exam)

        result = MockResult.objects.get(user=profile, mock_exam=exam)
        assert result.score == 4  # all answered "A" == correct_choice_key
        assert result.irt_theta is not None
        assert result.irt_scaled_score is not None
        assert result.points_delta is None  # CBT模試はポイント対象外

        res = client.get(f"/api/exams/{exam.id}/result/")
        assert res.status_code == 200
        assert res.json()["status"] == "graded"
        assert res.json()["irt_scaled_score"] == result.irt_scaled_score

        other_exam = make_exam(n_questions=2, kind=MockExam.Kind.CBT_ONCE, exam_type="CBT")
        blocked = client.post(f"/api/exams/{other_exam.id}/start/")
        assert blocked.status_code == 400


class TestMonthlyPoints:
    def test_grading_awards_points_and_updates_rank_pool(self):
        exam = make_exam(n_questions=4, kind=MockExam.Kind.MONTHLY, exam_type="CBT")
        c1, p1 = auth_client()
        c2, p2 = auth_client()
        start_and_answer_all(c1, exam, key="A")  # 全問正解
        start_and_answer_all(c2, exam, key="B")  # 全問不正解（correct_choice_keyはA）

        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")
        p1.refresh_from_db()
        p2.refresh_from_db()

        assert p1.ranked_matches == 1
        assert p2.ranked_matches == 1
        r1 = MockResult.objects.get(user=p1, mock_exam=exam)
        r2 = MockResult.objects.get(user=p2, mock_exam=exam)
        assert r1.points_delta > r2.points_delta
        # 累計ポイントは0スタート（D の 0%）。下限は0なので負けても0未満にならない。
        assert p1.points == max(0, STARTING_POINTS + r1.points_delta)
        assert p2.points == max(0, STARTING_POINTS + r2.points_delta)


class TestLargeExamDetail:
    def test_section_deviation_and_distribution(self):
        exam = make_exam(n_questions=4, kind=MockExam.Kind.LARGE, exam_type="KOKUSHI")
        c1, p1 = auth_client()
        c2, p2 = auth_client()
        start_and_answer_all(c1, exam, key="A")
        start_and_answer_all(c2, exam, key="B")
        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")

        r1 = MockResult.objects.get(user=p1, mock_exam=exam)
        assert r1.points_delta is None  # 大型模試はポイント対象外
        assert r1.section_deviation_scores  # 分野別偏差値が入っている
        assert r1.score_distribution["buckets"]
        assert r1.score_distribution["my_bucket"] is not None


class TestPointsRanking:
    def test_only_ranked_users_are_listed(self):
        client, profile = auth_client()
        unranked_client, _ = auth_client()  # ranked_matches=0 のまま
        profile.points = 1200
        profile.ranked_matches = 3
        profile.save(update_fields=["points", "ranked_matches"])

        res = client.get("/api/ranking/points/")
        assert res.status_code == 200
        body = res.json()
        assert len(body["entries"]) == 1  # 未ランクのユーザーは含まれない
        assert body["me"]["eligible"] is True
        assert body["me"]["tier"] == "SS"  # 母集団1人なら自分が最上位


class TestPointsRankingScope:
    def test_university_scope_filters_and_reports_reason_when_unset(self):
        from accounts.models import University

        uni = University.objects.create(name="ランキング大学")
        client, profile = auth_client(university=uni)
        profile.points = 1100
        profile.ranked_matches = 2
        profile.save(update_fields=["points", "ranked_matches"])

        other_client, other = auth_client()  # 別大学（未設定）、こちらもランク対象
        other.points = 1300
        other.ranked_matches = 1
        other.save(update_fields=["points", "ranked_matches"])

        res = client.get("/api/ranking/points/?scope=university")
        assert res.status_code == 200
        body = res.json()
        assert len(body["entries"]) == 1  # 他大学のユーザーは含まれない
        assert body["entries"][0]["display_name"] != ""

        no_uni_client, _ = auth_client()
        res2 = no_uni_client.get("/api/ranking/points/?scope=university")
        assert res2.json()["me"]["eligible"] is False


class TestExamGradeGating:
    """月次実力テストは、CBT版は1〜4年生限定・国試版は学年制限なし。
    1〜4年生は両方見え、5〜6年生は国試版だけが見える (spec)。"""

    def _create_monthly(self):
        # 出題プールが空だとコマンドが失敗するので、両方の試験種別を用意する。
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(40):
                make_question(
                    question_text=f"{exam_type}プール設問{i}",
                    correct_choice_key="A",
                    exam_type=exam_type,
                )
        call_command("create_scheduled_exam", "--kind", "monthly", "--open-now")
        return {e.exam_type: e for e in MockExam.objects.filter(kind=MockExam.Kind.MONTHLY)}

    def test_cbt_exam_targets_grades_1_to_4(self):
        exams = self._create_monthly()
        cbt = exams["CBT"]
        assert cbt.target_grade_min is None  # 下限なし = 1年生から
        assert cbt.target_grade_max == 4

    def test_kokushi_exam_has_no_grade_restriction(self):
        exams = self._create_monthly()
        kokushi = exams["KOKUSHI"]
        assert kokushi.target_grade_min is None
        assert kokushi.target_grade_max is None

    def test_fourth_year_sees_both_cbt_and_kokushi(self):
        self._create_monthly()
        client, _ = auth_client(grade=4)
        types = {e["exam_type"] for e in client.get("/api/exams/").json()}
        assert types == {"CBT", "KOKUSHI"}

    def test_fifth_year_sees_only_the_kokushi_exam(self):
        self._create_monthly()
        client, _ = auth_client(grade=5)
        types = {e["exam_type"] for e in client.get("/api/exams/").json()}
        assert types == {"KOKUSHI"}
