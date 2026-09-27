import json
import re

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

    @staticmethod
    def _write(tmp_path, questions):
        path = tmp_path / "batch.json"
        payload = {"meta": {"batch_id": "t"}, "questions": questions}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def _question(category="循環器", text="心不全の設問" * 5, choice_prefix="選択肢"):
        return {
            "id": "t-001",
            "exam_type": "CBT",
            "category": category,
            "question_text": text,
            "choices": [{"id": k, "text": f"{choice_prefix}{k}"} for k in "ABCDE"],
            "correct_choice_id": "B",
            "explanation": "解説" * 50,
        }

    def test_reimport_after_recategorizing_does_not_duplicate(self, tmp_path):
        """分野名を直してから取り込み直しても、同じ設問は増えない。

        以前は分野名と本文の組で既存の行を探していたので、分野名が変わると
        別の設問とみなして2つ目を作り、古い分野名の行も残っていた。演習画面で
        同じ科目が2行に分かれて出た原因の1つ。
        """
        call_command("import_questions", "--file", str(self._write(tmp_path, [self._question()])))
        call_command(
            "import_questions",
            "--file",
            str(self._write(tmp_path, [self._question(category="呼吸器")])),
        )
        assert Question.objects.filter(question_text="心不全の設問" * 5).count() == 1

    def test_same_stem_with_different_choices_are_separate_questions(self, tmp_path):
        """本文が同じでも選択肢が違えば別の設問（国試に実例がある）。"""
        stem = "医師の職業倫理に反するのはどれか。"
        questions = [
            self._question(text=stem, choice_prefix="第1問"),
            self._question(text=stem, choice_prefix="第2問"),
        ]
        call_command("import_questions", "--file", str(self._write(tmp_path, questions)))
        assert Question.objects.filter(question_text=stem).count() == 2


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
        # 同梱データに四連問は無い（2セットあったが単問にほどいた。
        # test_shipped_data.py の test_no_series_questions を参照）
        assert QuestionSet.objects.count() == 0
        assert not imported.filter(question_type=Question.QuestionType.SEQUENTIAL).exists()


class TestBundledBasicScienceBatch:
    """書き下ろしのCBT基礎医学バッチ(cbt_batch_basic_2026.json)。

    設問の本体は scripts/cbt_basic_questions/ にあり、JSON はそこから
    scripts/build_cbt_basic_batch.py で書き出す。JSON だけを直すと次に
    書き出したときに黙って消えるので、書き出し直した結果と一致することを見る。
    """

    def _scripts_dir(self):
        from pathlib import Path

        return Path(__file__).resolve().parents[2] / "scripts"

    def _batch(self):
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[1]
            / "quiz" / "management" / "commands" / "data" / "cbt_batch_basic_2026.json"
        )
        return path, json.loads(path.read_text(encoding="utf-8"))

    def test_passes_validator_without_bias_warnings(self):
        validator = TestBundledCoreBatch()._load_validator()
        _, batch = self._batch()
        report = validator.Report()
        validator.validate_schema(batch, report)
        validator.validate_items(batch, report)
        assert report.failures == [], report.failures
        # 正答の位置の偏りと「正答が最長」の偏りは、このバッチでは警告も出さない
        assert report.warnings == [], report.warnings

    def test_single_basic_science_questions_only(self):
        _, batch = self._batch()
        questions = batch["questions"]
        assert len(questions) >= 500
        assert not batch.get("question_sets")  # 四連問は作らない
        assert {q["question_type"] for q in questions} == {"M"}
        assert {q["category"] for q in questions} == {"基礎医学"}
        assert {q["blueprint_code"].split("-")[0] for q in questions} == {"C"}
        for q in questions:
            # 誤答4つそれぞれに理由がある（画面で選択肢の横に出す）
            wrong = {c["id"] for c in q["choices"]} - {q["correct_choice_id"]}
            assert set(q["distractor_rationale"]) == wrong, q["id"]

    def test_json_matches_source(self, tmp_path):
        import importlib.util
        import sys

        scripts_dir = self._scripts_dir()
        sys.path.insert(0, str(scripts_dir))
        try:
            spec = importlib.util.spec_from_file_location(
                "build_cbt_basic_batch", scripts_dir / "build_cbt_basic_batch.py"
            )
            builder = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(builder)
            out = tmp_path / "basic.json"
            builder.main(str(out))
        finally:
            sys.path.remove(str(scripts_dir))
        _, shipped = self._batch()
        assert json.loads(out.read_text(encoding="utf-8")) == shipped, (
            "scripts/cbt_basic_questions/ と同梱JSONがずれている。"
            "python scripts/build_cbt_basic_batch.py で書き出し直すこと"
        )

    def test_imports_as_pending(self):
        path, batch = self._batch()
        call_command("import_questions", "--file", str(path))
        imported = Question.objects.filter(source=Question.Source.LLM)
        assert imported.count() == len(batch["questions"])
        assert not imported.exclude(status=Question.Status.PENDING).exists()
        assert set(imported.values_list("category", flat=True)) == {"基礎医学"}


class TestBundledKokushiBatches:
    """同梱の国試バッチ(kokushi_*.json)に文字化けが混ざっていないことを保証する。

    国試PDFの本文フォントは ToUnicode を持たない部分集合が混ざっており、
    抽出器はそこを制御文字や別の字で埋めてしまう。実際に第114〜116回の268問が
    "\\x02か月の乳児"（正しくは "2か月の乳児"）や "全身Ø怠感"（倦怠感）の形で
    取り込まれていた。見た目が日本語のままなので気づきにくく、CIで止める。
    """

    EXAMS = tuple(range(106, 120))  # 第106〜119回

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
            # 国試の選択肢は通常ａ〜ｅの5つだが、ｆまである設問が稀にある
            # （第116回F75の「診断と死産届の組合せ」は3×2で6択）。
            assert 5 <= len(q["choices"]) <= 6, q["id"]
            keys = [c["id"] for c in q["choices"]]
            assert keys == list("ABCDEF"[: len(keys)]), q["id"]
            assert q["correct_choice_id"] in set(keys), q["id"]
            texts = [c["text"] for c in q["choices"]]
            assert len(set(texts)) == len(texts), q["id"]  # 選択肢の重複なし
            assert all(texts), q["id"]

    # 連問の症例文の続き（「その後の経過 ： …」「現症 ： …」）は、PDFでは前の
    # 設問の ｅ の直後に組まれる。取り込みで ｅ の続きとして読むと、選択肢が
    # 数百字になり、続きを要る次の設問からは症例が欠ける（第114回B43・B44）。
    CASE_SECTION = re.compile(r"現病歴\s*[:：]|その後の経過|検査所見\s*[:：]|現\s*症\s*[:：]|既往歴\s*[:：]")

    @pytest.mark.parametrize("exam", EXAMS)
    def test_choices_do_not_carry_case_text(self, exam):
        bad = []
        for q, _ in self._bodies(exam):
            for c in q["choices"]:
                text = c["text"]
                if len(text) > 150 or (len(text) > 60 and self.CASE_SECTION.search(text)):
                    bad.append(f"{q['id']} {c['id']}: {text[:40]}…（{len(text)}字）")
        assert not bad, "選択肢に症例文が付いている:\n" + "\n".join(bad)

    def test_corpus_size(self):
        # 縮小したら気づけるように下限を固定する
        total = sum(len(list(self._bodies(e))) for e in self.EXAMS)
        assert total >= 3300, total


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


class TestSeedDemoSamples:
    """seed_demo のサンプル設問。

    SAMPLE_QUESTIONS に question_text が無く、seed_demo の get_or_create の
    defaults にも入っていなかったため、本番に本文の無い設問が15問（CBT 10 /
    国試 5）できていた。モデルが blank=True なので保存でき、アプリ側は
    「（本文なし）」と出すだけで、気づけるところが無かった。
    """

    def test_every_sample_has_a_question_text(self):
        from quiz.management.commands.seed_demo import SAMPLE_QUESTIONS

        missing = [
            i for i, q in enumerate(SAMPLE_QUESTIONS, 1)
            if not (q.get("question_text") or "").strip()
        ]
        assert not missing, f"question_text の無いサンプル設問: {missing}"

    def test_seed_demo_writes_the_question_text(self, db):
        """defaults に入れ忘れると本文が空のまま作られる。"""
        from django.core.management import call_command

        from quiz.management.commands.seed_demo import SAMPLE_QUESTIONS
        from quiz.models import Question

        call_command("seed_demo")
        blank = Question.objects.filter(question_text="").count()
        assert blank == 0, f"本文が空の設問が {blank} 件できた"
        # サンプルの設問文がそのまま入っていること。
        for q in SAMPLE_QUESTIONS[:3]:
            assert Question.objects.filter(question_text=q["question_text"]).exists()

    def test_seed_demo_uses_each_exams_category_names(self, db):
        """見本の分野名は、その試験種別の科目名に寄せてから保存する。

        見本は「内分泌代謝」「消化器」と書いてあり、どちらも国試の科目名では
        ない（CBT でも「内分泌・代謝」）。そのまま入れると演習画面で同じ
        科目が別の行に分かれる。2回流しても見本は増えない。
        """
        from django.core.management import call_command

        from quiz.categories import CATEGORIES_BY_EXAM
        from quiz.models import Question

        call_command("seed_demo")
        call_command("seed_demo")
        for exam, names in CATEGORIES_BY_EXAM.items():
            stray = set(
                Question.objects.filter(exam_type=exam)
                .exclude(category__in=names)
                .values_list("category", flat=True)
            )
            assert not stray, f"{exam} に科目名でない分野: {stray}"
        from quiz.management.commands.seed_demo import SAMPLE_QUESTIONS

        assert Question.objects.count() == len(SAMPLE_QUESTIONS)

    def test_bundled_batch_stores_explanation_text(self, db):
        """build_explanation は組を返すので、そのまま解説に入れてはいけない。"""
        from django.core.management import call_command

        from quiz.models import Question

        call_command("seed_demo", "--with-batch")
        broken = Question.objects.filter(explanation__startswith="(").count()
        assert broken == 0, f"解説にタプルがそのまま入った設問: {broken}"
        assert Question.objects.exclude(choice_explanations={}).exists()

    def test_correct_answer_is_among_the_choices(self):
        """設問文を後から書いたので、正答と選択肢の対応が崩れていないか見る。"""
        from quiz.management.commands.seed_demo import SAMPLE_QUESTIONS

        for i, q in enumerate(SAMPLE_QUESTIONS, 1):
            keys = [c["key"] for c in q["choices"]]
            assert q["correct_choice_key"] in keys, f"{i}問目の正答が選択肢に無い"


@pytest.mark.django_db
class TestSeedEditorialQuestions:
    """同梱のレビュー済みバッチは公開状態で入る（seed_editorial_questions）。

    import_questions は生成したてのバッチを審査待ちで止めるが、本番では
    migrate しか流れないので、同梱済みのものがそこで止まると永久に
    出てこない。レビュー済みと決めたファイルだけを公開で入れる。
    """

    def seed(self):
        from django.core.management import call_command

        call_command("seed_editorial_questions", verbosity=0)

    def test_bundled_batches_are_published(self):
        from quiz.models import Question

        self.seed()

        seeded = Question.objects.filter(category__in=["放射線", "麻酔"])
        assert seeded.count() == 25
        assert not seeded.exclude(status=Question.Status.PUBLISHED).exists()

    def test_running_it_twice_does_not_duplicate(self):
        from quiz.models import Question

        self.seed()
        before = Question.objects.count()
        self.seed()

        assert Question.objects.count() == before

    def test_it_fills_the_thin_subjects(self):
        """放射線と麻酔は、既存の設問だけでは演習の単位にならなかった。

        本番のバンクにはこれに加えて、0018 で各科から集め直した設問が
        入る（CBT放射線2問・国試放射線7問・国試麻酔2問）。ここでは
        同梱バッチがそれぞれ何問ぶん足すかだけを見る。
        """
        from quiz.models import Question

        self.seed()

        assert Question.objects.filter(exam_type="CBT", category="放射線").count() == 10
        assert Question.objects.filter(exam_type="KOKUSHI", category="放射線").count() == 5
        assert Question.objects.filter(exam_type="KOKUSHI", category="麻酔").count() == 10

    def test_choice_explanations_come_along(self):
        from quiz.models import Question

        self.seed()

        for question in Question.objects.filter(category__in=["放射線", "麻酔"]):
            assert question.explanation
            # 正解以外の4つに、なぜ誤りかが入っている。
            assert len(question.choice_explanations) == 4


@pytest.mark.django_db
class TestStripStrayColumnSeparators:
    """語の途中に紛れ込んだ列区切りを落とす（マイグレーション 0020）。

    国試PDFの取り込みで、組合せ問題の列を見分けるために差し込む "—" が
    字間の広い箇所へ誤って入り、「Bell麻痺— の症状」になっていた。
    """

    def question(self, text, choices=None):
        from quiz.models import Question

        return Question.objects.create(
            category="医学総論",
            exam_type="KOKUSHI",
            difficulty=2,
            question_text=text,
            choices=choices or [{"key": k, "text": k} for k in "ABCDE"],
            correct_choice_key="A",
            explanation="",
            status=Question.Status.PUBLISHED,
        )

    def strip(self):
        import importlib

        from django.apps import apps as django_apps

        module = importlib.import_module(
            "quiz.migrations.0020_strip_stray_column_separators"
        )
        module.strip_separators(django_apps, None)

    def test_separators_inside_words_are_removed(self):
        q = self.question("Bell麻痺— の症状で誤って— いるのはどれか。")

        self.strip()

        q.refresh_from_db()
        assert q.question_text == "Bell麻痺の症状で誤っているのはどれか。"

    def test_a_separator_glued_to_the_next_word_is_removed(self):
        q = self.question("副腎腺腫による—Cushing症候群で認め—ないのはどれか。")

        self.strip()

        q.refresh_from_db()
        assert q.question_text == "副腎腺腫によるCushing症候群で認めないのはどれか。"

    def test_combination_choices_keep_the_column_separator(self):
        q = self.question(
            "職業性曝露と疾患の組合せとして最も適切なのはどれか。",
            [
                {"key": "A", "text": "石綿（アスベスト）— 悪性胸膜中皮腫"},
                {"key": "B", "text": "有機溶剤 — 珪肺"},
            ],
        )

        self.strip()

        q.refresh_from_db()
        assert [c["text"] for c in q.choices] == [
            "石綿（アスベスト） — 悪性胸膜中皮腫",
            "有機溶剤 — 珪肺",
        ]

    def test_a_doubled_separator_before_a_colon_is_dropped(self):
        q = self.question(
            "栄養管理として適切なのはどれか。",
            [{"key": "A", "text": "水分 — : 30mL/kg/日"}],
        )

        self.strip()

        q.refresh_from_db()
        assert q.choices[0]["text"] == "水分 : 30mL/kg/日"

    def test_a_correct_separator_is_left_alone(self):
        q = self.question("疾患と症状の組合せはどれか。", [{"key": "A", "text": "葉酸 — 巨赤芽球性貧血"}])

        self.strip()

        q.refresh_from_db()
        assert q.choices[0]["text"] == "葉酸 — 巨赤芽球性貧血"
