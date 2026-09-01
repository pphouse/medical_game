"""科目（category）を CBT / 国試それぞれの科目立てに沿って決められること。"""

import pytest

from quiz.categories import (
    BLUEPRINT_AREA_BY_EXAM,
    CATEGORIES_BY_EXAM,
    CBT,
    CBT_CATEGORIES,
    GENERIC_BY_EXAM,
    KOKUSHI,
    KOKUSHI_CATEGORIES,
    LEGACY_TO_GENERIC,
    SPLIT_SOURCES,
    categories_for,
    category_for_blueprint_code,
    category_sort_key,
    classify,
    default_category,
    normalize,
)


class TestTaxonomy:
    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_blueprint_table_points_at_that_exams_categories(self, exam):
        valid = set(CATEGORIES_BY_EXAM[exam])
        for area, name in BLUEPRINT_AREA_BY_EXAM[exam].items():
            assert name in valid, f"{exam} {area} -> {name} が科目一覧に無い"

    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_generic_table_points_at_that_exams_categories(self, exam):
        valid = set(CATEGORIES_BY_EXAM[exam])
        for generic, name in GENERIC_BY_EXAM[exam].items():
            assert name in valid, f"{exam} {generic} -> {name} が科目一覧に無い"

    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_default_category_is_valid(self, exam):
        assert default_category(exam) in CATEGORIES_BY_EXAM[exam]

    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_category_names_are_unique(self, exam):
        names = CATEGORIES_BY_EXAM[exam]
        assert len(set(names)) == len(names)

    def test_legacy_names_resolve_to_a_known_generic(self):
        for old, generic in LEGACY_TO_GENERIC.items():
            assert generic in GENERIC_BY_EXAM[CBT], f"{old} -> {generic} が未定義"

    def test_split_candidates_are_known_generics(self):
        for _old, (allowed, fallback) in SPLIT_SOURCES.items():
            assert fallback in allowed
            for target in allowed:
                assert target in GENERIC_BY_EXAM[CBT]

    def test_kokushi_follows_the_qb_chapters(self):
        for chapter in ("消化管", "肝・胆・膵", "免疫・膠原病", "必修問題"):
            assert chapter in KOKUSHI_CATEGORIES

    def test_emergency_toxicology_anesthesia_are_one_subject(self):
        """救急・中毒・麻酔は1科目にまとめてある。

        単独では国試4問（麻酔科）・0問（中毒）しかなく、科目として選んでも
        演習にならなかった。旧科目名が本番DBに残っているので、そちらからの
        読み替えも保つ。
        """
        for names in (KOKUSHI_CATEGORIES, CBT_CATEGORIES):
            assert "救急・中毒・麻酔" in names
            for gone in ("救急", "中毒", "麻酔科", "中毒・環境"):
                assert gone not in names, f"{gone} が残っている"
        for exam in (CBT, KOKUSHI):
            for generic in ("救急", "麻酔", "中毒・環境異常症"):
                assert GENERIC_BY_EXAM[exam][generic] == "救急・中毒・麻酔"
        # 本番DBに残る旧科目名からも辿り着けること。
        for old_name in ("中毒", "中毒・環境", "麻酔科", "救急・集中治療"):
            assert normalize(old_name, "", None, KOKUSHI) == "救急・中毒・麻酔"

    def test_cbt_follows_the_core_curriculum_volumes(self):
        for name in ("基礎医学", "医学総論・公衆衛生・診療の基本", "多選択肢・4連問"):
            assert name in CBT_CATEGORIES


class TestBlueprintCode:
    @pytest.mark.parametrize(
        ("code", "cbt", "kokushi"),
        [
            ("D-5-4)-(2)-③", "循環器", "循環器"),
            ("D-1", "血液", "血液"),
            ("D-4", "運動器", "整形外科"),
            ("D-8-1)", "腎・泌尿器", "腎・泌尿器"),
            ("D-9", "産婦人科", "婦人科・乳腺外科"),
            ("D-10", "産婦人科", "産科"),
            ("D-12", "内分泌・代謝", "代謝・内分泌"),
            ("D-15", "精神", "精神科"),
            ("E-2", "感染症", "感染症"),
            ("E-6", "救急・中毒・麻酔", "救急・中毒・麻酔"),
            ("E-7", "小児（成長と発達）", "小児科"),
            ("B-1", "医学総論・公衆衛生・診療の基本", "公衆衛生"),
            ("C-2", "基礎医学", "医学総論"),
            ("G-1", "多選択肢・4連問", "医学総論"),
        ],
    )
    def test_same_code_maps_per_exam(self, code, cbt, kokushi):
        """同じ出題基準コードでも、試験によって入る科目が違う。"""
        assert category_for_blueprint_code(code, CBT) == cbt
        assert category_for_blueprint_code(code, KOKUSHI) == kokushi

    @pytest.mark.parametrize("code", ["", None, "Z-9", "ZZZ"])
    def test_unknown_codes_give_nothing(self, code):
        assert category_for_blueprint_code(code, CBT) is None

    def test_section_only_codes_fall_back_to_the_section(self):
        """A/B/C/F/G は大区分ごとに1科目へまとめてあるので、枝番が無くても引ける。"""
        assert category_for_blueprint_code("F", CBT) == "医学総論・公衆衛生・診療の基本"
        assert category_for_blueprint_code("B", KOKUSHI) == "公衆衛生"

    def test_blueprint_code_beats_the_stored_category(self):
        assert normalize("循環器", "心電図所見", "D-8-1)", CBT) == "腎・泌尿器"

    def test_blueprint_code_beats_keywords(self):
        text = "疫学調査で罹患率とオッズ比を求めた。"
        assert normalize(None, text, "D-6", KOKUSHI) == "呼吸器"


class TestNormalize:
    def test_category_of_that_exam_is_left_alone(self):
        assert normalize("消化管", exam_type=KOKUSHI) == "消化管"
        assert normalize("基礎医学", exam_type=CBT) == "基礎医学"

    @pytest.mark.parametrize(
        ("old", "cbt", "kokushi"),
        [
            ("循環器系", "循環器", "循環器"),
            ("腎・尿路系", "腎・泌尿器", "腎・泌尿器"),
            ("運動器系", "運動器", "整形外科"),
            ("血液・造血器・リンパ系", "血液", "血液"),
            ("免疫・アレルギー・膠原病", "免疫・膠原病", "免疫・膠原病"),
            ("集団に対する医療", "医学総論・公衆衛生・診療の基本", "公衆衛生"),
            ("４連問", "多選択肢・4連問", "医学総論"),
        ],
    )
    def test_legacy_names_are_renamed_per_exam(self, old, cbt, kokushi):
        assert normalize(old, exam_type=CBT) == cbt
        assert normalize(old, exam_type=KOKUSHI) == kokushi

    def test_unknown_name_is_routed_by_keywords(self):
        text = "疫学調査で罹患率とオッズ比を求めた。"
        assert normalize("なにかの科目", text, exam_type=KOKUSHI) == "公衆衛生"

    def test_undecidable_falls_back_to_default(self):
        assert normalize("知らない科目", "特徴のない文章", exam_type=CBT) == default_category(CBT)
        assert normalize("知らない科目", "特徴のない文章", exam_type=KOKUSHI) == default_category(
            KOKUSHI
        )

    def test_unknown_exam_type_is_treated_as_cbt(self):
        assert normalize(None, "", "D-9", "OSCE") == "産婦人科"


class TestClassify:
    def test_returns_a_generic_organ_name(self):
        assert classify("疫学調査で罹患率とオッズ比を求めた。") in GENERIC_BY_EXAM[CBT]

    def test_no_match_returns_none(self):
        assert classify("特徴のない文章") is None


class TestSortKey:
    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_that_exams_order_is_followed(self, exam):
        names = categories_for(exam)
        assert tuple(sorted(names, key=lambda c: category_sort_key(c, exam))) == names

    def test_unknown_names_go_last(self):
        last = KOKUSHI_CATEGORIES[-1]
        assert category_sort_key("知らない科目", KOKUSHI) > category_sort_key(last, KOKUSHI)
