"""選択肢ごとの解説（Question.choice_explanations）。

正解・誤答それぞれが「なぜそうなのか」を選択肢の横に出せるよう、解説本文に
畳み込まず構造のまま持つ。
"""

import json

import pytest
from django.core.management import call_command

from quiz.choice_explanations import (
    BLOCK_HEADING,
    merge_into_text,
    split_choice_explanations,
)
from quiz.models import Question

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db

FOLDED = (
    "本文の解説。\n"
    "\n"
    f"{BLOCK_HEADING}\n"
    "B: 前壁中隔梗塞はV1〜V4のST上昇を示す。\n"
    "C: 側壁梗塞はI・aVL・V5・V6のST上昇を示す。\n"
    "E: 肺動脈は冠灌流に関与しない。"
)


class TestSplit:
    def test_it_pulls_the_block_out_of_the_body(self):
        body, per_choice = split_choice_explanations(FOLDED)
        assert body == "本文の解説。"
        assert per_choice == {
            "B": "前壁中隔梗塞はV1〜V4のST上昇を示す。",
            "C": "側壁梗塞はI・aVL・V5・V6のST上昇を示す。",
            "E": "肺動脈は冠灌流に関与しない。",
        }

    def test_a_wrapped_line_sticks_to_the_previous_choice(self):
        text = f"本文。\n\n{BLOCK_HEADING}\nB: 一行目\nそのつづき\nC: 別の選択肢"
        _, per_choice = split_choice_explanations(text)
        assert per_choice["B"] == "一行目 そのつづき"
        assert per_choice["C"] == "別の選択肢"

    def test_a_plain_explanation_is_left_alone(self):
        assert split_choice_explanations("ふつうの解説。") == ("ふつうの解説。", {})

    def test_a_colon_in_the_body_is_not_mistaken_for_a_choice(self):
        """見出しより前は見ないので、本文中の「A: 〜」は拾わない。"""
        body, per_choice = split_choice_explanations("所見A: 心雑音を認める。")
        assert body == "所見A: 心雑音を認める。"
        assert per_choice == {}

    def test_merge_round_trips(self):
        body, per_choice = split_choice_explanations(FOLDED)
        again, per_again = split_choice_explanations(merge_into_text(body, per_choice))
        assert (again, per_again) == (body, per_choice)


class TestImportKeepsThemStructured:
    def test_distractor_rationale_lands_in_its_own_field(self, tmp_path):
        batch = {
            "questions": [
                {
                    "category": "循環器",
                    "exam_type": "CBT",
                    "question_text": "選択肢解説つきの設問",
                    "choices": [{"id": k, "text": f"選択肢{k}"} for k in "ABCDE"],
                    "correct_choice_id": "A",
                    "explanation": "本文の解説。",
                    "distractor_rationale": {"B": "Bが誤りの理由", "C": "Cが誤りの理由"},
                }
            ]
        }
        path = tmp_path / "batch.json"
        path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

        call_command("import_questions", f"--file={path}", verbosity=0)

        q = Question.objects.get(question_text="選択肢解説つきの設問")
        assert q.choice_explanations == {"B": "Bが誤りの理由", "C": "Cが誤りの理由"}
        assert q.explanation == "本文の解説。"
        assert BLOCK_HEADING not in q.explanation


class TestApisReturnThem:
    def dirty(self):
        return make_question(
            question_text="選択肢解説つきの設問",
            correct_choice_key="A",
            explanation="本文の解説。",
            choice_explanations={"B": "Bが誤りの理由"},
        )

    def test_the_answer_response_carries_them(self):
        client, _ = auth_client()
        q = self.dirty()

        body = client.post(
            "/api/quiz/answers/",
            {
                "question_id": q.id,
                "selected_choice_key": "B",
                "response_time_ms": 100,
                "context": "solo",
            },
            format="json",
        ).json()

        assert body["choice_explanations"] == {"B": "Bが誤りの理由"}

    def test_the_exam_review_carries_them(self):
        from tests.test_exams import make_exam, start_and_answer_all

        client, _ = auth_client(grade=4)
        exam = make_exam(n_questions=2)
        Question.objects.filter(
            id__in=exam.mock_questions.values_list("question_id", flat=True)
        ).update(choice_explanations={"B": "Bが誤りの理由"})
        start_and_answer_all(client, exam, key="A")

        review = client.get(f"/api/exams/{exam.id}/result/").json()["review"]
        assert all(r["choice_explanations"] == {"B": "Bが誤りの理由"} for r in review)

    def test_the_battle_review_carries_them(self):
        from tests.test_battle import answer, current_round_id, make_room

        clients, _, code = make_room()
        Question.objects.all().update(choice_explanations={"B": "Bが誤りの理由"})
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)
        answer(clients[0], round_id, "A")
        answer(clients[1], round_id, "B")

        rows = clients[0].get(f"/api/battle/rooms/{code}/result/").json()["questions"]
        assert rows and all(r["choice_explanations"] == {"B": "Bが誤りの理由"} for r in rows)

    def test_they_are_not_leaked_before_answering(self):
        """演習中の一覧では、解説と同じく解答前には返さない。"""
        client, _ = auth_client()
        self.dirty()

        rows = client.get("/api/quiz/questions/?category=循環器").json()["results"]

        assert rows
        assert all("choice_explanations" not in r for r in rows)
        assert all("explanation" not in r for r in rows)


class TestCoverageReport:
    def test_it_counts_questions_with_every_distractor_explained(self):
        from quiz.management.commands.choice_explanation_coverage import coverage_rows

        make_question(
            question_text="全部そろっている設問",
            correct_choice_key="A",
            choice_explanations={k: "理由" for k in "BCDE"},
        )
        make_question(
            question_text="一部だけの設問",
            correct_choice_key="A",
            choice_explanations={"B": "理由"},
        )
        make_question(question_text="何も無い設問", correct_choice_key="A")

        row = next(r for r in coverage_rows("CBT") if r["category"] == "循環器")
        assert (row["full"], row["partial"], row["none"], row["total"]) == (1, 1, 1, 3)
