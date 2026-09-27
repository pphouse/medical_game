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
        for name in ("基礎医学", "医学総論・公衆衛生・診療の基本"):
            assert name in CBT_CATEGORIES

    def test_question_formats_are_not_categories(self):
        """多選択肢・4連問は出題形式の枠で、科目ではない。

        科目として置いていたとき、出題基準 G-1 の単問38問（小児の症例問題）が
        4連問でもないのにまとめてそこに入っていた。
        """
        assert "多選択肢・4連問" not in CBT_CATEGORIES
        assert category_for_blueprint_code("G-1", CBT) is None


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
            ("G-1", None, "医学総論"),
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
        """A/B/C/F は大区分ごとに1科目へまとめてあるので、枝番が無くても引ける。"""
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
            # 形式の名前なので、本文が無ければ既定の科目に落ちる。
            ("４連問", "医学総論・公衆衛生・診療の基本", "医学総論"),
        ],
    )
    def test_legacy_names_are_renamed_per_exam(self, old, cbt, kokushi):
        assert normalize(old, exam_type=CBT) == cbt
        assert normalize(old, exam_type=KOKUSHI) == kokushi

    @pytest.mark.parametrize(
        ("name", "exam", "expected"),
        [
            # 国試の科目名が CBT の設問に付いている
            ("小児科", CBT, "小児（成長と発達）"),
            ("整形外科", CBT, "運動器"),
            ("代謝・内分泌", CBT, "内分泌・代謝"),
            ("泌尿器科", CBT, "腎・泌尿器"),
            # CBT の科目名が国試の設問に付いている
            ("小児（成長と発達）", KOKUSHI, "小児科"),
            ("運動器", KOKUSHI, "整形外科"),
            ("内分泌・代謝", KOKUSHI, "代謝・内分泌"),
            ("眼", KOKUSHI, "眼科"),
        ],
    )
    def test_the_other_exams_name_is_translated(self, name, exam, expected):
        """もう一方の試験の科目名は、対応する科目へ読み替える。

        読み替えが無かったときは既定の科目（医学総論）に落ちていて、
        管理画面でも「小児科」に対して「医学総論…を指定してください」と
        見当違いの案内を出していた。
        """
        assert normalize(name, "", None, exam) == expected

    def test_split_names_across_exams_are_decided_by_the_text(self):
        """候補が2つに割れるものは本文で決める。"""
        assert normalize("産婦人科", "妊娠32週の妊婦。", None, KOKUSHI) == "産科"
        assert normalize("産婦人科", "子宮筋腫の患者。", None, KOKUSHI) == "婦人科・乳腺外科"
        assert normalize("消化器", "肝硬変の患者。", None, KOKUSHI) == "肝・胆・膵"

    def test_series_questions_go_to_the_organ_of_their_content(self):
        """旧名「４連問」の設問は、本文から臓器の科目へ入る。"""
        text = "心電図でST上昇を認め、急性心筋梗塞と診断した。"
        assert normalize("４連問", text, exam_type=CBT) == "循環器"
        assert normalize("多選択肢・4連問", text, exam_type=CBT) == "循環器"

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

    def test_kokushi_splits_hepatobiliary_out_of_the_gi_tract(self):
        """国試だけ「消化管」と「肝・胆・膵」を分ける（CBTは消化器のまま）。

        出題基準の D-7 は消化器系ひとまとめなので、コードだけでは分けられず
        本文の語で振り分ける。
        """
        liver = "60歳の男性。肝硬変による食道静脈瘤の破裂で搬送された。"
        gut = "40歳の女性。潰瘍性大腸炎の増悪で血便が続いている。"

        assert normalize("消化器", liver, exam_type=KOKUSHI) == "肝・胆・膵"
        assert normalize("消化器", gut, exam_type=KOKUSHI) == "消化管"
        # 出題基準コードがあっても本文で分ける
        assert normalize(None, liver, "D-7", KOKUSHI) == "肝・胆・膵"
        assert normalize(None, gut, "D-7", KOKUSHI) == "消化管"
        # CBT の科目立てには肝・胆・膵が無いので、どちらも消化器のまま
        assert normalize("消化器", liver, exam_type=CBT) == "消化器"
        assert normalize(None, liver, "D-7", CBT) == "消化器"

    def test_a_gi_question_without_hepatobiliary_words_stays_in_the_gi_tract(self):
        """腹痛・黄疸のような両方に出る語では肝胆膵に寄せないこと。"""
        assert normalize("消化管", "腹痛と黄疸を訴えている。", exam_type=KOKUSHI) == "消化管"


class TestClassify:
    def test_returns_a_generic_organ_name(self):
        assert classify("疫学調査で罹患率とオッズ比を求めた。") in GENERIC_BY_EXAM[CBT]

    def test_no_match_returns_none(self):
        assert classify("特徴のない文章") is None


class TestSortKey:
    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_major_subjects_come_first(self, exam):
        """メジャー科（内科系の主要科）を先頭にまとめる。"""
        from quiz.categories import is_major

        ordered = sorted(categories_for(exam), key=lambda c: category_sort_key(c, exam))
        flags = [is_major(c, exam) for c in ordered]
        # True が続いたあと False が続く（間で戻らない）
        assert flags == sorted(flags, reverse=True)
        assert flags[0] is True

    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_the_order_inside_each_group_is_the_exams_own(self, exam):
        """グループ内の並びは従来どおり（CBTは巻の順、国試はQBの章の順）。"""
        from quiz.categories import is_major

        names = categories_for(exam)
        ordered = sorted(names, key=lambda c: category_sort_key(c, exam))
        for major in (True, False):
            group = [c for c in ordered if is_major(c, exam) is major]
            assert group == [c for c in names if is_major(c, exam) is major]

    def test_unknown_names_go_last(self):
        last = KOKUSHI_CATEGORIES[-1]
        assert category_sort_key("知らない科目", KOKUSHI) > category_sort_key(last, KOKUSHI)

    def test_major_subjects_are_canonical_names(self):
        """科目名を変えたのにメジャー科の一覧を直し忘れると、静かに
        「その他」へ落ちるので、正規名であることを検査しておく。"""
        from quiz.categories import MAJOR_CATEGORIES_BY_EXAM

        for exam, majors in MAJOR_CATEGORIES_BY_EXAM.items():
            assert majors <= set(categories_for(exam))
            assert majors, exam
