import pytest

from quiz.models import AnswerHistory, Question
from tests.helpers import auth_client


def make_question(category, **kwargs):
    defaults = dict(
        topic="",
        exam_type=Question.ExamType.CBT,
        difficulty=Question.Difficulty.NORMAL,
        question_text=f"{category}の問題",
        choices=[{"key": k, "text": k} for k in "ABCDE"],
        correct_choice_key="A",
        explanation="",
        visibility=Question.Visibility.PUBLIC,
        status=Question.Status.PUBLISHED,
    )
    defaults.update(kwargs)
    return Question.objects.create(category=category, **defaults)


def answer(profile, question, mastery, times=1):
    for _ in range(times):
        AnswerHistory.objects.create(
            user=profile,
            question=question,
            correct=mastery in ("double_circle", "circle"),
            mastery_level=mastery,
            response_time_ms=1000,
            context="solo",
        )


@pytest.mark.django_db
class TestReviewFilter:
    def test_filters_by_multiple_categories(self):
        client, profile = auth_client()
        make_question("循環器")
        make_question("呼吸器")
        make_question("消化器")

        body = client.get("/api/quiz/review-filter/?categories=循環器,呼吸器").json()
        assert body["count"] == 2
        assert {q["category"] for q in body["results"]} == {"循環器", "呼吸器"}

    def test_filters_by_mastery(self):
        client, profile = auth_client()
        cross = make_question("循環器")
        circle = make_question("呼吸器")
        answer(profile, cross, "cross")
        answer(profile, circle, "circle")

        body = client.get("/api/quiz/review-filter/?mastery=cross").json()
        assert [q["id"] for q in body["results"]] == [cross.id]

    def test_unstudied_includes_never_answered(self):
        """一度も解いていない問題が「未演習」に入ること。"""
        client, profile = auth_client()
        never = make_question("循環器")
        done = make_question("呼吸器")
        answer(profile, done, "circle")

        body = client.get("/api/quiz/review-filter/?mastery=unstudied").json()
        assert [q["id"] for q in body["results"]] == [never.id]

    def test_unstudied_combines_with_other_levels(self):
        """未演習と✕を同時に選んだら両方が出る（OR）。ここが素直に書くと
        「未演習だけ」に潰れやすい。"""
        client, profile = auth_client()
        never = make_question("循環器")
        cross = make_question("呼吸器")
        circle = make_question("消化器")
        answer(profile, cross, "cross")
        answer(profile, circle, "circle")

        body = client.get("/api/quiz/review-filter/?mastery=unstudied,cross").json()
        assert {q["id"] for q in body["results"]} == {never.id, cross.id}

    def test_filters_by_attempt_count(self):
        client, profile = auth_client()
        once = make_question("循環器")
        twice = make_question("呼吸器")
        thrice = make_question("消化器")
        answer(profile, once, "cross", times=1)
        answer(profile, twice, "cross", times=2)
        answer(profile, thrice, "cross", times=4)

        one = client.get("/api/quiz/review-filter/?attempts=1").json()
        assert {q["id"] for q in one["results"]} == {once.id}

        two = client.get("/api/quiz/review-filter/?attempts=2").json()
        assert {q["id"] for q in two["results"]} == {twice.id}

        # 3plus は3回以上をまとめる（4回も含む）。
        three = client.get("/api/quiz/review-filter/?attempts=3plus").json()
        assert {q["id"] for q in three["results"]} == {thrice.id}

        combined = client.get("/api/quiz/review-filter/?attempts=1,3plus").json()
        assert {q["id"] for q in combined["results"]} == {once.id, thrice.id}

    def test_combines_all_filters(self):
        client, profile = auth_client()
        target = make_question("循環器")
        wrong_category = make_question("呼吸器")
        wrong_mastery = make_question("循環器")
        answer(profile, target, "cross", times=2)
        answer(profile, wrong_category, "cross", times=2)
        answer(profile, wrong_mastery, "circle", times=2)

        body = client.get(
            "/api/quiz/review-filter/?categories=循環器&mastery=cross&attempts=2"
        ).json()
        assert {q["id"] for q in body["results"]} == {target.id}

    def test_no_filters_returns_everything_visible(self):
        client, _ = auth_client()
        make_question("循環器")
        make_question("呼吸器")
        body = client.get("/api/quiz/review-filter/").json()
        assert body["count"] == 2

    def test_empty_param_is_treated_as_no_filter(self):
        """フロントで全解除すると categories= が飛ぶ。0件ではなく全件が正。"""
        client, _ = auth_client()
        make_question("循環器")
        body = client.get("/api/quiz/review-filter/?categories=").json()
        assert body["count"] == 1

    def test_rejects_unknown_mastery(self):
        client, _ = auth_client()
        res = client.get("/api/quiz/review-filter/?mastery=perfect")
        assert res.status_code == 400

    def test_rejects_unknown_attempt_bucket(self):
        client, _ = auth_client()
        res = client.get("/api/quiz/review-filter/?attempts=5")
        assert res.status_code == 400
