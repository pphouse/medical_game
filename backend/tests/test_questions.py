import json

import pytest
from django.core.management import call_command

from accounts.models import Profile
from quiz.models import Question, QuestionSet
from quiz.views import CORRECT_RATE_RECALC_EVERY

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db


def answer(client, question, key="A"):
    return client.post(
        "/api/quiz/answers/",
        {"question_id": question.id, "selected_choice_key": key, "response_time_ms": 1000},
        format="json",
    )


class TestPublicationGate:
    def test_only_published_questions_are_listed(self):
        client, _ = auth_client()
        make_question(question_text="公開済み")
        for status in ("draft", "pending", "rejected"):
            make_question(question_text=f"非公開 {status}", status=status)

        res = client.get("/api/quiz/questions/?category=循環器")
        assert res.status_code == 200
        texts = [q["question_text"] for q in res.json()["results"]]
        assert texts == ["公開済み"]

    def test_unpublished_question_cannot_be_answered(self):
        client, _ = auth_client()
        question = make_question(status="pending")
        assert answer(client, question).status_code == 404

    def test_pending_llm_question_requires_moderator_approval(self):
        question = make_question(status="pending", source="llm")
        student_client, _ = auth_client()
        assert (
            student_client.post(f"/api/quiz/review/questions/{question.id}/approve/").status_code
            == 403
        )

        mod_client, moderator = auth_client(role=Profile.Role.MODERATOR)
        res = mod_client.post(f"/api/quiz/review/questions/{question.id}/approve/")
        assert res.status_code == 200
        question.refresh_from_db()
        assert question.status == Question.Status.PUBLISHED
        assert question.reviewed_by == moderator
        assert question.reviewed_at is not None

    def test_review_queue_lists_pending(self):
        make_question(status="pending", question_text="審査待ちの設問")
        make_question(question_text="公開済みの設問")
        mod_client, _ = auth_client(role=Profile.Role.MODERATOR)
        res = mod_client.get("/api/quiz/review/questions/")
        rows = res.json()["results"]
        assert [q["question_text"] for q in rows] == ["審査待ちの設問"]
        # moderation serializer exposes the answer for review
        assert rows[0]["correct_choice_key"] == "A"


class TestCorrectRate:
    def test_correct_rate_null_until_min_answers(self):
        client, _ = auth_client()
        question = make_question()
        res = answer(client, question)
        assert res.json()["correct_rate"] is None

        list_res = client.get("/api/quiz/questions/?category=循環器")
        assert list_res.json()["results"][0]["correct_rate"] is None

    def test_answer_count_increments_and_rate_recalcs_every_n(self):
        client, _ = auth_client()
        question = make_question()
        for i in range(CORRECT_RATE_RECALC_EVERY):
            key = "A" if i % 2 == 0 else "B"  # 半分正解
            answer(client, question, key=key)
        question.refresh_from_db()
        assert question.answer_count == CORRECT_RATE_RECALC_EVERY
        assert question.correct_rate == 50.0
        # 10問到達後は API でも公開される
        res = client.get("/api/quiz/questions/?category=循環器")
        assert res.json()["results"][0]["correct_rate"] == 50.0


class TestMasteryFilter:
    def test_latest_answer_wins_with_distinct_on(self):
        client, _ = auth_client()
        question = make_question()
        answer(client, question, key="B")  # 不正解 -> cross
        answer(client, question, key="A")  # 正解 -> circle が最新

        res = client.get("/api/quiz/questions/?category=循環器&mastery_level=cross")
        assert res.json()["results"] == []
        res = client.get("/api/quiz/questions/?category=循環器&mastery_level=circle")
        assert [q["id"] for q in res.json()["results"]] == [question.id]

    def test_unstudied_filter_excludes_answered(self):
        client, _ = auth_client()
        answered = make_question(question_text="解答済み")
        unanswered = make_question(question_text="未解答")
        answer(client, answered)

        res = client.get("/api/quiz/questions/?category=循環器&mastery_level=unstudied")
        assert [q["id"] for q in res.json()["results"]] == [unanswered.id]


class TestImportCommand:
    def test_import_forces_pending_and_creates_sets(self, tmp_path):
        batch = {
            "meta": {"generated_at": "2026-07-23T00:00:00Z", "generator": "test", "batch_id": "t"},
            "questions": [
                {
                    "id": "t-001",
                    "exam_type": "CBT",
                    "category": "循環器",
                    "disease": "心不全",
                    "question_text": "テスト設問" * 10,
                    "choices": [{"id": k, "text": f"選択肢{k}"} for k in "ABCDE"],
                    "correct_choice_id": "B",
                    "explanation": "解説" * 50,
                    "distractor_rationale": {"A": "誤り", "C": "誤り", "D": "誤り", "E": "誤り"},
                }
            ],
            "question_sets": [
                {
                    "id": "t-set-001",
                    "category": "消化器",
                    "disease": "急性虫垂炎",
                    "case_stem": "18歳男性。12時間前からの臍周囲痛で来院した。",
                    "steps": [
                        {
                            "set_order": order,
                            "phase": phase,
                            "question_text": f"{phase}で最も適切なのはどれか。",
                            "choices": [{"id": k, "text": f"{phase}{k}"} for k in "ABCDE"],
                            "correct_choice_id": "C",
                            "explanation": "解説" * 50,
                        }
                        for order, phase in enumerate(
                            ["医療面接", "身体診察", "検査", "病態生理"], start=1
                        )
                    ],
                }
            ],
        }
        path = tmp_path / "batch.json"
        path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

        call_command("import_questions", "--file", str(path))

        imported = Question.objects.get(question_text="テスト設問" * 10)
        assert imported.status == Question.Status.PENDING  # 強制 (spec 2-1)
        assert imported.source == Question.Source.LLM
        # 選択肢ごとの解説は本文に畳み込まず、専用の項目に構造のまま入る
        # （選択肢の横に並べて表示するため）。
        assert imported.choice_explanations == {
            "A": "誤り", "C": "誤り", "D": "誤り", "E": "誤り",
        }
        assert "誤答選択肢の解説" not in imported.explanation
        # choices are converted to the DB-canonical {"key","text"} form
        assert imported.choices[0] == {"key": "A", "text": "選択肢A"}

        qset = QuestionSet.objects.get()
        steps = list(qset.questions.order_by("set_order"))
        assert [s.set_order for s in steps] == [1, 2, 3, 4]
        assert all(s.status == Question.Status.PENDING for s in steps)
        assert all(s.question_type == Question.QuestionType.SEQUENTIAL for s in steps)


class TestBundledCoreBatch:
    """同梱の編集バッチ(cbt_batch_core_2026.json)が検証器の必須ゲートを
    通ることを CI で保証する。問題バンクの品質デグレをここで検出する。"""

    def _load_validator(self):
        import importlib.util
        from pathlib import Path

        scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
        spec = importlib.util.spec_from_file_location(
            "validate_questions", scripts_dir / "validate_questions.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _batch_path(self):
        from pathlib import Path

        return (
            Path(__file__).resolve().parents[1]
            / "quiz" / "management" / "commands" / "data" / "cbt_batch_core_2026.json"
        )

    def test_bundled_batch_passes_validator(self):
        validator = self._load_validator()
        batch = json.loads(self._batch_path().read_text(encoding="utf-8"))

        report = validator.Report()
        validator.validate_schema(batch, report)
        validator.validate_items(batch, report)

        # 構造・長さ・禁止語・重複・キー分布の必須ゲートに fail がないこと
        assert report.failures == [], report.failures

        # 規模と分野の広がり（縮小したら気づけるように下限を固定）
        assert len(batch["questions"]) >= 300
        categories = {q["category"] for q in batch["questions"]}
        assert len(categories) >= 12, categories

    def test_bundled_batch_imports_as_pending(self):
        call_command(
            "import_questions", "--file", str(self._batch_path())
        )
        imported = Question.objects.filter(source=Question.Source.LLM)
        # すべて審査待ちで入る（人手レビュー前に出題されない, spec 2-1）
        assert imported.count() >= 300
        assert not imported.exclude(status=Question.Status.PENDING).exists()
        # 四連問が2セット取り込まれている
        assert QuestionSet.objects.count() == 2


class TestBundledKokushiBatches:
    """同梱の国試バッチ(kokushi_*.json)に文字化けが混ざっていないことを保証する。

    国試PDFの本文フォントは ToUnicode を持たない部分集合が混ざっており、
    抽出器はそこを制御文字や別の字で埋めてしまう。実際に第114〜116回の268問が
    "\\x02か月の乳児"（正しくは "2か月の乳児"）や "全身Ø怠感"（倦怠感）の形で
    取り込まれていた。見た目が日本語のままなので気づきにくく、CIで止める。
    """

    EXAMS = (114, 115, 116, 117, 118, 119)

    def _batch_path(self, exam):
        from pathlib import Path

        return (
            Path(__file__).resolve().parents[1]
            / "quiz" / "management" / "commands" / "data" / f"kokushi_{exam}.json"
        )

    def _bodies(self, exam):
        batch = json.loads(self._batch_path(exam).read_text(encoding="utf-8"))
        for q in batch["questions"]:
            yield q, q["question_text"] + "".join(c["text"] for c in q["choices"])

    @pytest.mark.parametrize("exam", EXAMS)
    def test_no_unresolved_glyphs(self, exam):
        import importlib.util
        from pathlib import Path

        scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
        spec = importlib.util.spec_from_file_location(
            "import_kokushi", scripts_dir / "import_kokushi.py"
        )
        importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(importer)

        for q, body in self._bodies(exam):
            assert not importer.is_unusable(body), f"{q['id']}: {body[:80]!r}"
            assert not importer.has_broken_glyph(body), f"{q['id']}: {body[:80]!r}"

    @pytest.mark.parametrize("exam", EXAMS)
    def test_ids_are_unique(self, exam):
        # 同じ設問番号を2度拾うのは切り出しの誤り。取り込み時に落としている。
        ids = [q["id"] for q, _ in self._bodies(exam)]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("exam", EXAMS)
    def test_questions_are_well_formed(self, exam):
        for q, _ in self._bodies(exam):
            assert len(q["choices"]) == 5, q["id"]
            assert q["correct_choice_id"] in {"A", "B", "C", "D", "E"}, q["id"]
            texts = [c["text"] for c in q["choices"]]
            assert len(set(texts)) == 5, q["id"]
            assert all(texts), q["id"]

    def test_corpus_size(self):
        # 縮小したら気づけるように下限を固定する
        total = sum(len(list(self._bodies(e))) for e in self.EXAMS)
        assert total >= 1000, total


class TestExamTypeFilter:
    """CBT と国試を分けて選べること (分野一覧・問題一覧の両方)。

    分野の切り方が試験ごとに違ううえ、同名の分野に両方の問題が入るため、
    混ざったままだと目的の問題に辿り着けない。
    """

    def _seed(self):
        make_question(category="循環器系", exam_type="CBT", question_text="CBTの循環器問題")
        make_question(category="循環器系", exam_type="KOKUSHI", question_text="国試の循環器問題")
        make_question(
            category="医師国家試験（分類未確定）", exam_type="KOKUSHI", question_text="国試の未分類問題"
        )

    def test_progress_defaults_to_all_exam_types(self):
        client, _ = auth_client()
        self._seed()

        rows = client.get("/api/quiz/progress/").json()
        by_category = {r["category"]: r["total"] for r in rows}
        assert by_category["循環器系"] == 2
        assert by_category["医師国家試験（分類未確定）"] == 1

    def test_progress_filtered_by_exam_type(self):
        client, _ = auth_client()
        self._seed()

        cbt = {r["category"]: r["total"] for r in client.get("/api/quiz/progress/?exam_type=CBT").json()}
        assert cbt == {"循環器系": 1}

        kokushi = {
            r["category"]: r["total"]
            for r in client.get("/api/quiz/progress/?exam_type=KOKUSHI").json()
        }
        assert kokushi == {"循環器系": 1, "医師国家試験（分類未確定）": 1}

    def test_question_list_filtered_by_exam_type(self):
        client, _ = auth_client()
        self._seed()

        res = client.get("/api/quiz/questions/?category=循環器系&exam_type=KOKUSHI")
        assert res.status_code == 200
        results = res.json()["results"]
        assert [q["question_text"] for q in results] == ["国試の循環器問題"]
