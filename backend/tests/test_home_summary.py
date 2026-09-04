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
from quiz.models import Question

from .helpers import auth_client

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
