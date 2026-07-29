import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import University
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
        call_command("create_scheduled_exam", "--open-now", "--count", "8")
        exam = MockExam.objects.get()
        assert exam.mock_questions.count() == 8
        areas = {
            mq.question.blueprint_code[:3] for mq in exam.mock_questions.all()
        }
        assert areas == {"D-5", "D-7"}
        assert exam.effective_status() == MockExam.Status.OPEN
