"""解説の定型文を落とす処理のテスト。"""

import pytest

from quiz.explanations import strip_boilerplate
from quiz.models import Question

from .helpers import make_question

pytestmark = pytest.mark.django_db

IMPORTED = (
    "正答は B「腹部大動脈瘤」。\n"
    "\n"
    "この設問は医師国家試験の過去問です。詳しい解説は準備中で、内容の確認後に順次追加されます。\n"
    "\n"
    "出典：厚生労働省ホームページ 第118回医師国家試験 A001\n"
    "https://www.mhlw.go.jp/seisakunitsuite/bunya/kenkou_iryou/iryou/topics/tp240424-01.html\n"
    "（設問文および選択肢は本アプリの表示形式に整形しています）"
)


class TestStripBoilerplate:
    def test_it_drops_the_source_url_and_the_formatting_note(self):
        cleaned = strip_boilerplate(IMPORTED)
        assert "https://" not in cleaned
        assert "表示形式" not in cleaned
        # 出典（どの回のどの問題か）は残す
        assert "第118回医師国家試験 A001" in cleaned
        assert cleaned.startswith("正答は B「腹部大動脈瘤」。")
        # 行を抜いた跡に空行を残さない
        assert not cleaned.endswith("\n")
        assert "\n\n\n" not in cleaned

    def test_it_drops_the_editorial_note(self):
        text = (
            "解説本文。\n"
            "\n"
            "※この解説はアプリ編集部が作成したものです。"
            "厚生労働省が公表する過去問には解説は含まれません。"
        )
        assert strip_boilerplate(text) == "解説本文。"

    def test_it_keeps_a_url_that_is_part_of_a_sentence(self):
        """本文中のURLは消さない（行まるごと定型文のときだけ落とす）。"""
        text = "詳細は https://example.com/guideline を参照のこと。"
        assert strip_boilerplate(text) == text

    def test_it_is_idempotent(self):
        once = strip_boilerplate(IMPORTED)
        assert strip_boilerplate(once) == once

    def test_empty_explanation_is_left_alone(self):
        assert strip_boilerplate("") == ""


class TestStripBoilerplateVariants:
    """取り込み時期で書式が揺れているので、どの書き方でも落とすこと。"""

    def test_the_url_and_note_on_one_line(self):
        text = (
            "正答は B。\n"
            "出典：厚生労働省ホームページ 第117回医師国家試験 A001 "
            "https://www.mhlw.go.jp/a.html／設問文および選択肢を本アプリの表示形式に整形"
        )
        cleaned = strip_boilerplate(text)
        assert "https://" not in cleaned
        assert "表示形式" not in cleaned
        assert cleaned.endswith("第117回医師国家試験 A001")

    def test_the_note_without_parentheses_or_desu_masu(self):
        assert strip_boilerplate(
            "解説本文。\n設問文および選択肢を本アプリの表示形式に整形"
        ) == "解説本文。"

    def test_the_editorial_note_on_the_same_line_as_the_body(self):
        assert strip_boilerplate(
            "解説本文。※この解説はアプリ編集部が作成したものです。"
            "厚生労働省が公表する過去問には解説は含まれません。"
        ) == "解説本文。"

    def test_a_source_line_without_a_url_is_kept_whole(self):
        text = "出典：厚生労働省ホームページ 第119回医師国家試験 B012"
        assert strip_boilerplate(text) == text

    def test_a_reference_url_outside_a_source_line_survives(self):
        text = "詳細は https://example.com/guideline を参照のこと。"
        assert strip_boilerplate(text) == text

    def test_nothing_is_left_but_the_body_when_everything_is_boilerplate(self):
        assert strip_boilerplate(
            "https://www.mhlw.go.jp/a.html\n（設問文および選択肢は本アプリの表示形式に整形しています）"
        ) == ""


class TestExplanationsAreCleanOnEveryApi:
    """掃除を流していないデータベースでも、返す時点で定型文が消えること。"""

    def dirty_question(self):
        return make_question(explanation=IMPORTED, question_text="定型文つきの設問")

    def test_the_answer_response_is_clean(self):
        from tests.helpers import auth_client

        client, _ = auth_client()
        q = self.dirty_question()
        # 掃除コマンドを通さず、DBには定型文が残ったままにする
        Question.objects.filter(pk=q.pk).update(explanation=IMPORTED)

        body = client.post(
            "/api/quiz/answers/",
            {
                "question_id": q.id,
                "selected_choice_key": "A",
                "response_time_ms": 100,
                "context": "solo",
            },
            format="json",
        ).json()

        assert "https://" not in body["explanation"]
        assert "表示形式" not in body["explanation"]
        assert Question.objects.get(pk=q.pk).explanation == IMPORTED  # DBは触らない


class TestStripCommand:
    def test_the_command_cleans_existing_questions(self):
        from django.core.management import call_command

        q = make_question(explanation=IMPORTED)
        untouched = make_question(explanation="ふつうの解説", question_text="別の設問")

        call_command("strip_explanation_boilerplate", verbosity=0)

        q.refresh_from_db()
        untouched.refresh_from_db()
        assert "https://" not in q.explanation
        assert untouched.explanation == "ふつうの解説"

    def test_dry_run_does_not_save(self):
        from django.core.management import call_command

        q = make_question(explanation=IMPORTED)
        call_command("strip_explanation_boilerplate", "--dry-run", verbosity=0)
        q.refresh_from_db()
        assert q.explanation == IMPORTED


class TestImportStripsBoilerplate:
    def test_imported_questions_have_no_boilerplate(self, tmp_path):
        import json

        from django.core.management import call_command

        batch = {
            "questions": [
                {
                    "category": "循環器",
                    "exam_type": "KOKUSHI",
                    "question_text": "取り込みテストの設問",
                    "choices": [
                        {"id": "A", "text": "あ"},
                        {"id": "B", "text": "い"},
                    ],
                    "correct_choice_id": "B",
                    "explanation": IMPORTED,
                }
            ]
        }
        path = tmp_path / "batch.json"
        path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

        call_command("import_questions", f"--file={path}", verbosity=0)

        q = Question.objects.get(question_text="取り込みテストの設問")
        assert "https://" not in q.explanation
        assert "表示形式" not in q.explanation
        assert "第118回医師国家試験 A001" in q.explanation


class TestExamAndBattleExplanationsAreClean:
    """模試の見直しと対戦の振り返りでも定型文を出さないこと。"""

    def test_the_exam_result_review_is_clean(self):
        from tests.helpers import auth_client
        from tests.test_exams import make_exam, start_and_answer_all

        client, _ = auth_client(grade=4)
        exam = make_exam(n_questions=2)
        Question.objects.filter(
            id__in=exam.mock_questions.values_list("question_id", flat=True)
        ).update(explanation=IMPORTED)
        start_and_answer_all(client, exam, key="A")

        review = client.get(f"/api/exams/{exam.id}/result/").json()["review"]

        assert review
        for row in review:
            assert "https://" not in row["explanation"]
            assert "表示形式" not in row["explanation"]

    def test_the_battle_result_review_is_clean(self):
        from tests.test_battle import answer, current_round_id, make_room

        clients, _, code = make_room()
        Question.objects.all().update(explanation=IMPORTED)
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)
        answer(clients[0], round_id, "A")
        answer(clients[1], round_id, "B")

        rows = clients[0].get(f"/api/battle/rooms/{code}/result/").json()["questions"]

        assert rows
        for row in rows:
            assert "https://" not in row["explanation"]
            assert "表示形式" not in row["explanation"]
