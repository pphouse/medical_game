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


@pytest.mark.django_db
class TestSourceFilter:
    """模試復習・対戦復習の入口。そこで解いたことのある問題だけを対象にする。"""

    def test_source_limits_to_questions_answered_in_that_context(self):
        client, profile = auth_client()
        in_mock = make_question("循環器")
        in_battle = make_question("呼吸器")
        never = make_question("消化器")
        answer(profile, in_mock, "unstudied")  # context=solo で1件
        AnswerHistory.objects.filter(question=in_mock).update(context="mock")
        answer(profile, in_battle, "cross")
        AnswerHistory.objects.filter(question=in_battle).update(context="battle")

        mock = client.get("/api/quiz/review-filter/?source=mock").json()
        battle = client.get("/api/quiz/review-filter/?source=battle").json()

        assert [q["id"] for q in mock["results"]] == [in_mock.id]
        assert [q["id"] for q in battle["results"]] == [in_battle.id]
        # 絞り込まなければ全部出る
        assert client.get("/api/quiz/review-filter/").json()["count"] == 3
        assert never.id not in {q["id"] for q in mock["results"]}

    def test_another_users_history_does_not_leak_in(self):
        client, _ = auth_client()
        other_client, other = auth_client(display_name="ほかの人")
        question = make_question("循環器")
        answer(other, question, "cross")
        AnswerHistory.objects.filter(question=question).update(context="mock")

        assert client.get("/api/quiz/review-filter/?source=mock").json()["count"] == 0
        assert other_client.get("/api/quiz/review-filter/?source=mock").json()["count"] == 1

    def test_it_grows_as_more_questions_are_answered(self):
        """模試や対戦を重ねるたび、復習の対象が増えていくこと。"""
        client, profile = auth_client()
        first = make_question("循環器")
        second = make_question("呼吸器")
        answer(profile, first, "unstudied")
        AnswerHistory.objects.filter(question=first).update(context="mock")
        assert client.get("/api/quiz/review-filter/?source=mock").json()["count"] == 1

        answer(profile, second, "unstudied")
        AnswerHistory.objects.filter(question=second).update(context="mock")
        assert client.get("/api/quiz/review-filter/?source=mock").json()["count"] == 2

    def test_available_categories_come_from_the_source_not_the_whole_bank(self):
        """科目チップに、その入口で選べない科目を並べないこと。"""
        client, profile = auth_client()
        in_mock = make_question("循環器")
        make_question("呼吸器")
        make_question("消化器")
        answer(profile, in_mock, "unstudied")
        AnswerHistory.objects.filter(question=in_mock).update(context="mock")

        body = client.get("/api/quiz/review-filter/?source=mock").json()
        assert body["available_categories"] == ["循環器"]
        # 絞り込みなしなら全科目
        whole = client.get("/api/quiz/review-filter/").json()
        assert whole["available_categories"] == ["呼吸器", "循環器", "消化器"]

    def test_available_categories_ignore_the_category_filter_itself(self):
        """科目を選んでも、選び直せるようチップの並びは変わらないこと。"""
        client, _ = auth_client()
        make_question("循環器")
        make_question("呼吸器")

        body = client.get("/api/quiz/review-filter/?categories=循環器").json()
        assert body["count"] == 1
        assert body["available_categories"] == ["呼吸器", "循環器"]

    def test_source_can_be_combined_with_the_other_filters(self):
        client, profile = auth_client()
        weak = make_question("循環器")
        strong = make_question("呼吸器")
        for q, level in ((weak, "cross"), (strong, "double_circle")):
            answer(profile, q, level)
            AnswerHistory.objects.filter(question=q).update(context="mock")

        body = client.get("/api/quiz/review-filter/?source=mock&mastery=cross").json()
        assert [q["id"] for q in body["results"]] == [weak.id]

    def test_an_unknown_source_is_rejected(self):
        client, _ = auth_client()
        assert client.get("/api/quiz/review-filter/?source=nope").status_code == 400
