"""科目ごとの問題数の偏りをならす仕組みのテスト。

「最低どの科目も15問」＋「残りは本番の出題構成比で比例配分」という方針
（quiz/blueprint_weights）が、目標値の算出と模試の出題抽選の両方で
効いていることを確かめる。
"""

import pytest

from quiz.blueprint_weights import (
    CBT_WEIGHTS,
    KOKUSHI_WEIGHTS,
    MIN_QUESTIONS_PER_CATEGORY,
    share_of,
    target_counts,
)
from quiz.categories import CBT_CATEGORIES, KOKUSHI_CATEGORIES

from .helpers import make_question

pytestmark = pytest.mark.django_db


class TestBlueprintWeights:
    def test_every_canonical_category_has_a_weight(self):
        """重みの無い科目があると、目標問題数にも模試にも出てこなくなる。"""
        assert set(CBT_WEIGHTS) == set(CBT_CATEGORIES)
        assert set(KOKUSHI_WEIGHTS) == set(KOKUSHI_CATEGORIES)
        assert all(w > 0 for w in CBT_WEIGHTS.values())
        assert all(w > 0 for w in KOKUSHI_WEIGHTS.values())

    @pytest.mark.parametrize(
        "exam_type,categories",
        [("CBT", CBT_CATEGORIES), ("KOKUSHI", KOKUSHI_CATEGORIES)],
    )
    def test_every_category_gets_at_least_the_minimum(self, exam_type, categories):
        targets = target_counts(exam_type, 2000)
        assert set(targets) == set(categories)
        assert min(targets.values()) >= MIN_QUESTIONS_PER_CATEGORY

    def test_targets_add_up_to_the_requested_total(self):
        for total in (1000, 1234, 2000):
            assert sum(target_counts("CBT", total).values()) == total

    def test_a_small_total_still_guarantees_the_minimum(self):
        """最低数の確保は比率より優先する（総数が足りなくても15問は積む）。"""
        targets = target_counts("KOKUSHI", 10)
        assert set(targets.values()) == {MIN_QUESTIONS_PER_CATEGORY}

    def test_extra_questions_follow_the_exam_blueprint_not_the_bank(self):
        """上積みは出題構成比の順に多くなる（必修 > 循環器 > 麻酔科）。"""
        targets = target_counts("KOKUSHI", 2000)
        assert targets["必修問題"] > targets["循環器"] > targets["麻酔科"]
        assert share_of("KOKUSHI", "必修問題") > share_of("KOKUSHI", "麻酔科")

    def test_unknown_exam_type_has_no_weights(self):
        assert target_counts("UNKNOWN", 100) == {}
        assert share_of("UNKNOWN", "循環器") == 0.0


class TestQuestionTargetsReport:
    def test_report_shows_the_shortfall_against_the_target(self):
        from quiz.management.commands.question_targets import report_for

        for i in range(3):
            make_question(category="循環器", exam_type="CBT", question_text=f"循環器{i}")

        rows = {r["category"]: r for r in report_for("CBT", total=2000)}
        assert rows["循環器"]["current"] == 3
        assert rows["循環器"]["shortfall"] == rows["循環器"]["target"] - 3
        # 1問も無い科目は目標がそのまま不足になる
        assert rows["皮膚"]["current"] == 0
        assert rows["皮膚"]["shortfall"] == rows["皮膚"]["target"]

    def test_report_covers_every_category_even_with_an_empty_bank(self):
        from quiz.management.commands.question_targets import report_for

        rows = report_for("KOKUSHI")
        assert {r["category"] for r in rows} == set(KOKUSHI_CATEGORIES)
        assert all(r["target"] >= MIN_QUESTIONS_PER_CATEGORY for r in rows)


class TestExamSamplingUsesTheBlueprint:
    def test_an_over_represented_category_does_not_dominate_the_exam(self):
        """バンクが偏っていても、模試の出題は構成比どおりに近づくこと。"""
        from exams.management.commands.create_scheduled_exam import pick_pool

        # 医学総論だけ極端に多いバンク（実測の偏りを再現）
        pool = [
            make_question(
                category="医学総論・公衆衛生・診療の基本",
                exam_type="CBT",
                question_text=f"総論{i}",
            )
            for i in range(200)
        ]
        for category in ("循環器", "呼吸器", "消化器", "神経"):
            pool += [
                make_question(category=category, exam_type="CBT", question_text=f"{category}{i}")
                for i in range(50)
            ]

        picked = pick_pool(pool, 100, exam_type="CBT")
        assert len(picked) == 100
        n_general = sum(
            1 for q in picked if q.category == "医学総論・公衆衛生・診療の基本"
        )
        # バンクでは半数(200/400)を占めるので、バンク比で配ると50問になる。
        # 本番の構成比で配れば、プールにある5科目の中での重み
        # (50 : 22+20+22+16) から4割弱に収まる。
        assert 30 <= n_general <= 45

    def test_it_still_fills_the_count_when_a_category_runs_out(self):
        """構成比の割り当てが在庫を超える科目があっても、必要数はそろえる。"""
        from exams.management.commands.create_scheduled_exam import pick_pool

        pool = [
            make_question(category="循環器", exam_type="CBT", question_text=f"循環器{i}")
            for i in range(5)
        ]
        pool += [
            make_question(category="皮膚", exam_type="CBT", question_text=f"皮膚{i}")
            for i in range(45)
        ]
        picked = pick_pool(pool, 40, exam_type="CBT")
        assert len(picked) == 40
        assert len({q.id for q in picked}) == 40

    def test_categories_outside_the_weight_table_are_not_shut_out(self):
        """仮設問の「未分類」のような科目も出題対象から外れないこと。"""
        from exams.management.commands.create_scheduled_exam import pick_pool

        pool = [
            make_question(category="未分類", exam_type="CBT", question_text=f"未分類{i}")
            for i in range(30)
        ]
        picked = pick_pool(pool, 20, exam_type="CBT")
        assert len(picked) == 20
