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
