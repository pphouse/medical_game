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
        for chapter in ("消化管", "肝・胆・膵", "免疫・膠原病", "公衆衛生"):
            assert chapter in KOKUSHI_CATEGORIES

    def test_emergency_and_toxicology_are_one_subject(self):
        """救急と中毒は1科目にまとめてある。

        中毒は単独では0問で、科目として選んでも演習にならなかった。
        旧科目名が本番DBに残っているので、そちらからの読み替えも保つ。
        """
        for names in (KOKUSHI_CATEGORIES, CBT_CATEGORIES):
            for gone in ("救急", "中毒", "麻酔科", "中毒・環境"):
                assert gone not in names, f"{gone} が残っている"
        assert "救急・中毒" in KOKUSHI_CATEGORIES
        # CBTには麻酔の設問が無いので、3科目まとめたままにしてある。
        assert "救急・中毒・麻酔" in CBT_CATEGORIES
        for generic in ("救急", "中毒・環境異常症"):
            assert GENERIC_BY_EXAM[CBT][generic] == "救急・中毒・麻酔"
            assert GENERIC_BY_EXAM[KOKUSHI][generic] == "救急・中毒"
        # 本番DBに残る旧科目名からも辿り着けること。
        for old_name in ("中毒", "中毒・環境", "救急・集中治療"):
            assert normalize(old_name, "", None, KOKUSHI) == "救急・中毒"

    def test_anesthesia_is_a_subject_of_its_own_in_kokushi(self):
        """麻酔は国試だけ独立した科目。

        設問を足して10問を超えたので救急・中毒から分けた。CBTには麻酔の
        設問が無いので、そちらは救急・中毒・麻酔のままにしてある。
        """
        assert "麻酔" in KOKUSHI_CATEGORIES
        assert "麻酔" not in CBT_CATEGORIES
        assert GENERIC_BY_EXAM[KOKUSHI]["麻酔"] == "麻酔"
        assert GENERIC_BY_EXAM[CBT]["麻酔"] == "救急・中毒・麻酔"
        assert normalize("麻酔科", "", None, KOKUSHI) == "麻酔"
        assert normalize("麻酔科", "", None, CBT) == "救急・中毒・麻酔"

    def test_radiology_is_a_subject_in_both_exams(self):
        """放射線は両方の試験で科目にしてある（設問を足して10問を超えた）。"""
        for names in (KOKUSHI_CATEGORIES, CBT_CATEGORIES):
            assert "放射線" in names
        for exam in (CBT, KOKUSHI):
            assert GENERIC_BY_EXAM[exam]["放射線"] == "放射線"
            assert normalize("放射線科", "", None, exam) == "放射線"

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
            ("D-8-1)", "腎臓", "腎臓"),
            ("D-9", "産婦人科", "婦人科・乳腺外科"),
            ("D-10", "産婦人科", "産科"),
            ("D-12", "内分泌・代謝", "代謝・内分泌"),
            ("D-15", "精神", "精神科"),
            ("E-2", "感染症", "感染症"),
            ("E-6", "救急・中毒・麻酔", "救急・中毒"),
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
        assert normalize("循環器", "心電図所見", "D-8-1)", CBT) == "腎臓"

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
            ("腎・尿路系", "腎臓", "腎臓"),
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
            ("泌尿器科", CBT, "泌尿器"),
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

    def test_the_retired_kidney_urology_name_is_split_by_the_text(self):
        """科目を分ける前の「腎・泌尿器」は、本文で腎臓／泌尿器に振り分ける。

        読み替えが無かったときは、本文に手掛かりが無いと既定の科目
        （医学総論）に落ちていた。
        """
        assert normalize("腎・泌尿器", "前立腺肥大症で排尿困難がある。", None, CBT) == "泌尿器"
        assert normalize("腎・泌尿器", "ネフローゼ症候群で浮腫がある。", None, KOKUSHI) == "腎臓"
        assert normalize("腎・泌尿器", "", None, CBT) == "腎臓"

    def test_stored_urology_survives_the_renal_blueprint_code(self):
        """出題基準 D-8 は腎臓に引けるが、分野名が泌尿器ならそのまま通す。

        本文に泌尿器の語が無い「尿失禁の分類」が、取り込み直すたびに
        腎臓へ戻されていた。
        """
        assert normalize("泌尿器", "尿失禁の分類として正しいのはどれか。", "D-8", CBT) == "泌尿器"

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


class TestDisplayOrderPriorities:
    """一覧の並びで決めていること。

    出題数の多い循環器・消化器系・内分泌代謝・腎を先頭寄りに置き、公衆衛生は
    一番下に置く。CBT の多選択肢・4連問は形式の枠で科目ではないので、一覧に無い。
    """

    def order(self, exam):
        return sorted(categories_for(exam), key=lambda c: category_sort_key(c, exam))

    def test_cbt_starts_with_the_heavy_organ_subjects(self):
        assert self.order(CBT)[:6] == [
            "循環器", "消化器", "内分泌・代謝", "呼吸器", "腎臓", "泌尿器",
        ]

    def test_kokushi_starts_with_the_heavy_organ_subjects(self):
        assert self.order(KOKUSHI)[:7] == [
            "循環器", "消化管", "肝・胆・膵", "代謝・内分泌", "呼吸器", "腎臓", "泌尿器",
        ]

    def test_the_digestive_subject_is_second(self):
        """消化器はどちらの試験でも上から2番目。"""
        assert self.order(CBT)[1] == "消化器"
        assert self.order(KOKUSHI)[1] == "消化管"

    def test_the_kidney_subject_comes_right_after_the_respiratory_one(self):
        """腎臓・泌尿器は呼吸器の次。

        CBTでは5番目、国試では6番目になる（国試は消化器が消化管と
        肝・胆・膵に分かれているぶん1つずれる）。
        """
        assert self.order(CBT)[3:6] == ["呼吸器", "腎臓", "泌尿器"]
        assert self.order(KOKUSHI)[4:7] == ["呼吸器", "腎臓", "泌尿器"]

    def test_both_exams_follow_the_same_order(self):
        """科目名は違っても、並びはCBTと国試で同じにする。

        探す位置が試験ごとに変わると、同じ科目を毎回探し直すことになる。
        国試で2つに分かれる科目（消化器→消化管/肝・胆・膵、産婦人科→
        婦人科・乳腺外科/産科）はCBTの位置に並べて置き、CBTにしかない
        腫瘍・基礎医学は国試では医学総論に含まれる。
        """
        # CBTの科目 -> 国試で対応する科目（複数に分かれるものは並びの順）
        same = [
            ("循環器", ["循環器"]),
            ("消化器", ["消化管", "肝・胆・膵"]),
            ("内分泌・代謝", ["代謝・内分泌"]),
            ("呼吸器", ["呼吸器"]),
            ("腎臓", ["腎臓"]),
            ("泌尿器", ["泌尿器"]),
            ("神経", ["神経"]),
            ("血液", ["血液"]),
            ("免疫・膠原病", ["免疫・膠原病"]),
            ("感染症", ["感染症"]),
            ("腫瘍", []),
            ("基礎医学", []),
            ("皮膚", ["皮膚科"]),
            ("運動器", ["整形外科"]),
            ("眼", ["眼科"]),
            ("耳鼻咽喉", ["耳鼻咽喉科"]),
            ("精神", ["精神科"]),
            ("小児（成長と発達）", ["小児科"]),
            ("産婦人科", ["婦人科・乳腺外科", "産科"]),
            ("救急・中毒・麻酔", ["救急・中毒", "麻酔"]),
            ("放射線", ["放射線"]),
            ("医学総論・公衆衛生・診療の基本", ["医学総論", "公衆衛生"]),
        ]
        assert self.order(CBT) == [cbt for cbt, _ in same]
        assert self.order(KOKUSHI) == [k for _, ks in same for k in ks]

    def test_public_health_is_last(self):
        # CBTの公衆衛生は医学総論・診療の基本とひとまとめの科目。
        assert self.order(CBT)[-1] == "医学総論・公衆衛生・診療の基本"
        assert self.order(KOKUSHI)[-1] == "公衆衛生"


@pytest.mark.django_db
class TestLegacyToxicologyIsMerged:
    """旧分野「中毒・環境異常症」は「救急・中毒・麻酔」に寄せる。

    救急・中毒・麻酔科は1つの科目なので、同じ中身が2つに割れて一覧に並ぶと
    どちらを開けばいいのか分からない。
    """

    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_the_legacy_name_normalizes_to_the_merged_subject(self, exam):
        from quiz.categories import normalize

        expected = "救急・中毒・麻酔" if exam == CBT else "救急・中毒"
        assert normalize("中毒・環境異常症", exam_type=exam) == expected

    def test_it_is_not_a_subject_of_its_own(self):
        assert "中毒・環境異常症" not in categories_for(CBT)
        assert "中毒・環境異常症" not in categories_for(KOKUSHI)

    def test_existing_questions_are_moved(self):
        """マイグレーションと同じ内容を流し直しても結果が変わらないこと。"""
        from django.core.management import call_command

        from quiz.models import Question

        Question.objects.create(
            category="中毒・環境異常症",
            exam_type="CBT",
            difficulty=2,
            question_text="旧分野のままの設問",
            choices=[{"key": k, "text": k} for k in "ABCDE"],
            correct_choice_key="A",
            explanation="",
            status=Question.Status.PUBLISHED,
        )

        call_command("reclassify_categories", verbosity=0)

        assert not Question.objects.filter(category="中毒・環境異常症").exists()
        assert Question.objects.filter(category="救急・中毒・麻酔").count() == 1


@pytest.mark.django_db
class TestRadiologySubjectQuestions:
    """放射線そのものを主題にした設問は「放射線科」に入れる。

    症例の中で画像検査や放射線治療が手段として出てくるだけの問題は、
    各論の科目に残す（肺癌の治療方針は呼吸器、など）。
    """

    def question(self, category, text):
        from quiz.models import Question

        return Question.objects.create(
            category=category,
            exam_type="KOKUSHI",
            difficulty=2,
            question_text=text,
            choices=[{"key": k, "text": k} for k in "ABCDE"],
            correct_choice_key="A",
            explanation="",
            status=Question.Status.PUBLISHED,
        )

    def run_migration_logic(self):
        """マイグレーション 0014 と同じ条件で振り分ける。"""
        import importlib

        from django.apps import apps as django_apps

        module = importlib.import_module(
            "quiz.migrations.0014_reclassify_radiology_questions"
        )
        module.move_to_radiology(django_apps, None)

    def test_radiation_subject_questions_move(self):
        from quiz.models import Question

        self.question("産科", "100mGy以上の放射線被曝が原因で胎児奇形が起こる時期はどれか。")
        self.question("神経", "転移性脳腫瘍の治療で、定位放射線照射が適切なのはどれか。")

        self.run_migration_logic()

        assert Question.objects.filter(category="放射線科").count() == 2

    def test_clinical_cases_that_merely_use_imaging_stay_put(self):
        from quiz.models import Question

        self.question("呼吸器", "72歳の男性。臨床病期IA期の原発性肺腺癌と診断された。放射線治療を含む方針を検討する。")
        self.question("消化管", "87歳の男性。造影剤を用いた上部消化管造影で狭窄を認めた。")

        self.run_migration_logic()

        assert not Question.objects.filter(category="放射線科").exists()
        assert Question.objects.filter(category="呼吸器").count() == 1
        assert Question.objects.filter(category="消化管").count() == 1


@pytest.mark.django_db
class TestKidneyAndUrologyAreSeparate:
    """腎臓（内科）と泌尿器（外科）は別の科目にする。

    診る科が違うのでまとめてあると目的の分野を探しにくい。出題基準の
    D-8 は腎・尿路ひとまとめなので、本文の語で振り分ける。
    """

    def test_both_are_subjects(self):
        for exam in (CBT, KOKUSHI):
            assert "腎臓" in categories_for(exam)
            assert "泌尿器" in categories_for(exam)
            assert "腎・泌尿器" not in categories_for(exam)

    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("70歳の男性。前立腺癌の疑いで紹介された。", "泌尿器"),
            ("尿管結石の治療で正しいのはどれか。", "泌尿器"),
            ("膀胱尿管逆流症で正しいのはどれか。", "泌尿器"),
            ("ネフローゼ症候群で浮腫をきたす機序はどれか。", "腎臓"),
            ("慢性糸球体腎炎の組織所見はどれか。", "腎臓"),
        ],
    )
    def test_the_blueprint_code_is_split_by_the_text(self, exam, text, expected):
        from quiz.categories import normalize

        assert normalize(None, text, "D-8", exam) == expected

    def test_a_named_kidney_category_is_left_alone(self):
        """分野名で腎臓だと分かっているものは本文を見ずにそのまま通す。"""
        from quiz.categories import normalize

        assert normalize("腎臓", "前立腺の記述を含む文章", exam_type=KOKUSHI) == "腎臓"

    @pytest.mark.parametrize("name", ["泌尿器科", "泌尿器", "泌尿器系"])
    @pytest.mark.parametrize("exam", [CBT, KOKUSHI])
    def test_urology_legacy_names_resolve_to_urology(self, exam, name):
        from quiz.categories import normalize

        assert normalize(name, exam_type=exam) == "泌尿器"

    def test_existing_questions_are_split(self):
        import importlib

        from django.apps import apps as django_apps

        from quiz.models import Question

        for text in ("前立腺肥大症の治療はどれか。", "急性糸球体腎炎の所見はどれか。"):
            Question.objects.create(
                category="腎・泌尿器",
                exam_type="KOKUSHI",
                difficulty=2,
                question_text=text,
                choices=[{"key": k, "text": k} for k in "ABCDE"],
                correct_choice_key="A",
                explanation="",
                status=Question.Status.PUBLISHED,
            )

        module = importlib.import_module("quiz.migrations.0017_split_kidney_and_urology")
        module.split(django_apps, None)

        assert Question.objects.filter(category="泌尿器").count() == 1
        assert Question.objects.filter(category="腎臓").count() == 1
        assert not Question.objects.filter(category="腎・泌尿器").exists()

    def test_the_blueprint_weights_cover_both(self):
        from quiz.blueprint_weights import CBT_WEIGHTS, KOKUSHI_WEIGHTS

        for weights in (CBT_WEIGHTS, KOKUSHI_WEIGHTS):
            assert "腎・泌尿器" not in weights
            assert weights["腎臓"] > weights["泌尿器"] > 0


@pytest.mark.django_db
class TestEverySubjectHasEnoughQuestions:
    """演習の単位として成立するよう、問題数が少なすぎる科目は残さない。

    国試の免疫・膠原病(7)・放射線科(7)・必修問題(0)が10問に届いていなかった。
    膠原病は他の科に散っていた設問を集め、残り2つは医学総論へ統合した。
    """

    def question(self, category, text, exam="KOKUSHI"):
        from quiz.models import Question

        return Question.objects.create(
            category=category,
            exam_type=exam,
            difficulty=2,
            question_text=text,
            choices=[{"key": k, "text": k} for k in "ABCDE"],
            correct_choice_key="A",
            explanation="",
            status=Question.Status.PUBLISHED,
        )

    def consolidate(self):
        import importlib

        from django.apps import apps as django_apps

        module = importlib.import_module("quiz.migrations.0016_consolidate_small_subjects")
        module.consolidate(django_apps, None)

    def test_small_subjects_are_gone_from_the_taxonomy(self):
        for dropped in ("放射線科", "必修問題"):
            assert dropped not in categories_for(KOKUSHI)

    def test_the_name_for_essentials_still_resolves_somewhere_sensible(self):
        """「必修問題」は分野ではなく出題形式の呼び名なので総論に落とす。"""
        from quiz.categories import normalize

        assert normalize("必修問題", exam_type=KOKUSHI) == "医学総論"
        assert normalize("必修問題", exam_type=CBT) == "医学総論・公衆衛生・診療の基本"

    def test_radiology_and_essentials_move_to_general_medicine(self):
        from quiz.models import Question

        self.question("放射線科", "被曝線量が最も多い検査はどれか。")
        self.question("必修問題", "必修のままだった設問。")

        self.consolidate()

        assert Question.objects.filter(category="医学総論").count() == 2
        assert not Question.objects.filter(category__in=["放射線科", "必修問題"]).exists()

    def test_immunology_questions_are_gathered(self):
        from quiz.models import Question

        self.question("呼吸器", "関節リウマチの関節外症状としてみられないのはどれか。")
        self.question("産科", "抗リン脂質抗体症候群で正しいのはどれか。")

        self.consolidate()

        assert Question.objects.filter(category="免疫・膠原病").count() == 2

    def test_clinical_cases_stay_in_their_organ_subject(self):
        """合併症として膠原病が出てくる症例は各論に残す。"""
        from quiz.models import Question

        self.question("産科", "34歳の初産婦。抗リン脂質抗体症候群の既往があり妊娠13週で受診した。")
        self.question("整形外科", "68歳の女性。関節リウマチのため通院中で、腰背部痛を主訴に来院した。")

        self.consolidate()

        assert not Question.objects.filter(category="免疫・膠原病").exists()
        assert Question.objects.filter(category="産科").count() == 1
        assert Question.objects.filter(category="整形外科").count() == 1


@pytest.mark.django_db
class TestRadiologyAndAnesthesiaSplit:
    """放射線と麻酔を独立した科目に切り出す（マイグレーション 0019）。

    画像や全身麻酔は各科の臨床問題にも普通に出てくるので、本文に語が在る
    だけでは移さない。「何を問うているか」＝設問の最後の一文で判断する。
    """

    def question(self, category, text, exam="KOKUSHI"):
        from quiz.models import Question

        return Question.objects.create(
            category=category,
            exam_type=exam,
            difficulty=2,
            question_text=text,
            choices=[{"key": k, "text": k} for k in "ABCDE"],
            correct_choice_key="A",
            explanation="",
            status=Question.Status.PUBLISHED,
        )

    def split(self):
        import importlib

        from django.apps import apps as django_apps

        module = importlib.import_module(
            "quiz.migrations.0019_split_radiology_and_anesthesia"
        )
        module.split(django_apps, None)

    def test_the_merged_kokushi_subject_is_renamed(self):
        from quiz.models import Question

        self.question("救急・中毒・麻酔", "熱中症の初期対応はどれか。")

        self.split()

        assert Question.objects.filter(category="救急・中毒").count() == 1
        assert not Question.objects.filter(category="救急・中毒・麻酔").exists()

    def test_anesthesia_questions_move_out_of_emergency(self):
        from quiz.models import Question

        self.question("救急・中毒・麻酔", "全身麻酔の導入で正しいのはどれか。")

        self.split()

        assert Question.objects.filter(category="麻酔").count() == 1

    def test_cbt_keeps_the_merged_subject(self):
        """CBTには麻酔の設問が無いので、3科目まとめたままにする。"""
        from quiz.models import Question

        self.question("救急・中毒・麻酔", "熱傷の重症度はどれか。", exam="CBT")

        self.split()

        assert Question.objects.filter(category="救急・中毒・麻酔").count() == 1

    def test_radiation_subject_questions_move_in_both_exams(self):
        from quiz.models import Question

        self.question("医学総論", "被曝線量が最も多い検査はどれか。")
        self.question("腫瘍", "放射線治療の特徴はどれか。", exam="CBT")

        self.split()

        assert Question.objects.filter(category="放射線").count() == 2

    def test_clinical_cases_that_merely_use_imaging_or_anesthesia_stay_put(self):
        from quiz.models import Question

        self.question("呼吸器", "72歳の男性。肺腺癌に放射線治療を行った。合併症はどれか。")
        self.question("整形外科", "65歳の女性。全身麻酔で人工膝関節置換術を受けた。原因はどれか。")

        self.split()

        assert not Question.objects.filter(category__in=["放射線", "麻酔"]).exists()
        assert Question.objects.filter(category="呼吸器").count() == 1
        assert Question.objects.filter(category="整形外科").count() == 1

    def test_the_blueprint_weights_cover_the_new_subjects(self):
        from quiz.blueprint_weights import CBT_WEIGHTS, KOKUSHI_WEIGHTS

        assert CBT_WEIGHTS["放射線"] > 0
        assert KOKUSHI_WEIGHTS["放射線"] > 0
        assert KOKUSHI_WEIGHTS["麻酔"] > 0
        assert "救急・中毒・麻酔" not in KOKUSHI_WEIGHTS
