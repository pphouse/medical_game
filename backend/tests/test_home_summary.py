"""ホーム（問題演習トップ）のサマリー: 進捗％と学内/全国順位。

順位まわりは RankingView（ランキング画面）と同じく同学年の中での順位に
している（対戦ランクとは違う演習だけの特別扱い、exams/ranking_utils 参照）。
ここで検証するのは HomeSummaryView 独自の snapshot_rank 実装が
RankingView と同じ仕様（学年未設定はランキング対象外・他学年は数えない）
になっていること。
"""

import pytest
from django.core.management import call_command

from accounts.models import Profile
from quiz.models import AnswerHistory, Question

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db


def make_questions(n, category="循環器"):
    return Question.objects.bulk_create(
        Question(
            category=category,
            exam_type="CBT",
            difficulty=2,
            question_text=f"設問{category}{i}",
            choices=[{"key": k, "text": f"選択肢{k}"} for k in "ABCDE"],
            correct_choice_key="A",
            explanation="解説",
            status=Question.Status.PUBLISHED,
        )
        for i in range(n)
    )


def seed_answers(profile, questions, correct=True):
    from quiz.models import AnswerHistory

    AnswerHistory.objects.bulk_create(
        AnswerHistory(
            user=profile,
            question=q,
            mastery_level="circle" if correct else "cross",
            correct=correct,
            response_time_ms=5000,
        )
        for q in questions
    )


class TestHomeSummaryRank:
    def test_grade_unset_has_no_rank(self):
        client, profile = auth_client(display_name="学年未設定")
        body = client.get("/api/quiz/summary/").json()
        assert body["national_rank"]["rank"] is None
        assert body["national_rank"]["out_of"] == 0

    def test_national_rank_is_scoped_to_same_grade(self):
        questions = make_questions(5)
        top_other_grade = Profile.objects.create(
            id="00000000-0000-0000-0000-000000000010", grade=6
        )
        seed_answers(top_other_grade, questions, correct=True)

        client, profile = auth_client(display_name="4年生", grade=4)
        seed_answers(profile, questions[:2], correct=True)

        call_command("aggregate_rankings", "--period", "all")

        body = client.get("/api/quiz/summary/").json()
        # 他学年の猛者を数えなければ1位・母集団1人のはず。
        assert body["national_rank"]["rank"] == 1
        assert body["national_rank"]["out_of"] == 1


@pytest.mark.django_db
class TestCategoryProgressAccuracy:
    """分野の一覧に、その分野での自分の正答率を出すこと。"""

    def answer(self, profile, question, correct):
        AnswerHistory.objects.create(
            user=profile,
            question=question,
            correct=correct,
            mastery_level="circle" if correct else "cross",
            response_time_ms=1000,
            context="solo",
        )

    def rows(self, client):
        return {r["category"]: r for r in client.get("/api/quiz/progress/").json()}

    def test_it_reports_the_rate_for_each_category(self):
        client, profile = auth_client()
        cardio = [make_question(category="循環器", question_text=f"循環器{i}") for i in range(4)]
        lung = [make_question(category="呼吸器", question_text=f"呼吸器{i}") for i in range(2)]
        for q, correct in zip(cardio, [True, True, True, False], strict=True):
            self.answer(profile, q, correct)
        for q in lung:
            self.answer(profile, q, False)

        rows = self.rows(client)

        assert rows["循環器"]["correct_rate"] == 75.0
        assert rows["呼吸器"]["correct_rate"] == 0.0

    def test_an_untouched_category_is_null_not_zero(self):
        """0%（全問不正解）と「まだ解いていない」を取り違えないこと。"""
        client, _ = auth_client()
        make_question(category="循環器", question_text="未演習の設問")

        assert self.rows(client)["循環器"]["correct_rate"] is None

    def test_another_users_answers_do_not_count(self):
        client, _ = auth_client()
        _, other = auth_client(display_name="ほかの人")
        q = make_question(category="循環器", question_text="他人が解いた設問")
        self.answer(other, q, True)

        assert self.rows(client)["循環器"]["correct_rate"] is None

    def test_every_attempt_counts_not_just_the_latest(self):
        """同じ問題を2回解けば2回ぶん母数に入る（ホームの全体正答率と同じ）。"""
        client, profile = auth_client()
        q = make_question(category="循環器", question_text="2回解く設問")
        self.answer(profile, q, False)
        self.answer(profile, q, True)

        assert self.rows(client)["循環器"]["correct_rate"] == 50.0
