import pytest

from quiz.categories import (
    CANONICAL_CATEGORIES,
    CATEGORY_ORDER,
    DEFAULT_CATEGORY,
    LEGACY_EXACT,
    SPLIT_SOURCES,
    category_sort_key,
    classify,
    normalize,
)
from quiz.models import Question


class TestTaxonomy:
    def test_legacy_map_only_points_at_canonical_names(self):
        for old, new in LEGACY_EXACT.items():
            assert new in CATEGORY_ORDER, f"{old} -> {new} が正規名でない"

    def test_split_targets_are_canonical(self):
        for old, (allowed, fallback) in SPLIT_SOURCES.items():
            assert fallback in allowed, f"{old} の既定値が候補に含まれない"
            for target in allowed:
                assert target in CATEGORY_ORDER, f"{old} -> {target} が正規名でない"

    def test_default_category_is_canonical(self):
        assert DEFAULT_CATEGORY in CATEGORY_ORDER

    def test_canonical_names_are_unique(self):
        assert len(set(CANONICAL_CATEGORIES)) == len(CANONICAL_CATEGORIES)


class TestNormalize:
    def test_canonical_name_is_left_alone(self):
        assert normalize("循環器", "") == "循環器"

    @pytest.mark.parametrize(
        ("old", "expected"),
        [
            ("呼吸器系", "呼吸器"),
            ("腎・尿路系", "腎臓"),  # 決め手がなければ既定側
            ("運動器系", "整形"),
            ("血液・造血器・リンパ系", "血液"),
            ("免疫・アレルギー・膠原病", "免疫"),
            ("集団に対する医療", "公衆衛生"),
            ("医の倫理と患者の権利、医師としての責務", "公衆衛生"),
        ],
    )
    def test_legacy_names_are_renamed(self, old, expected):
        assert normalize(old, "") == expected

    def test_obgyn_splits_into_obstetrics_and_gynecology(self):
        assert normalize("産婦人科系", "妊娠36週の妊婦。分娩の進行が停止した。") == "産科"
        assert normalize("産婦人科系", "42歳女性。過多月経と子宮筋腫を指摘された。") == "婦人科"

    def test_renal_splits_into_kidney_and_urology(self):
        assert normalize("腎・尿路系", "IgA腎症が疑われ腎生検を行った。") == "腎臓"
        assert normalize("腎・尿路系", "前立腺癌の疑いで生検を行った。") == "泌尿器"

    def test_split_never_escapes_its_two_candidates(self):
        """本文に他分野の語（心電図など）があっても候補外へは飛ばさない。"""
        result = normalize("腎・尿路系", "心電図でST上昇を認め、冠動脈造影を行った。")
        assert result in ("腎臓", "泌尿器")

    def test_unclassified_falls_back_to_default(self):
        assert normalize("医師国家試験（分類未確定）", "あああ") == DEFAULT_CATEGORY

    def test_unclassified_is_routed_by_keywords(self):
        assert normalize("医師国家試験（分類未確定）", "急性心筋梗塞で冠動脈を再灌流した。") == "循環器"

    def test_unknown_name_is_routed_by_keywords(self):
        assert normalize("知らない分野", "気管支喘息の発作で来院した。") == "呼吸器"


class TestClassify:
    def test_returns_none_when_nothing_matches(self):
        assert classify("あああ") is None

    def test_allowed_restricts_the_candidates(self):
        # 循環器の語しかないが、候補を産科/婦人科に絞れば選ばれない。
        assert classify("心筋梗塞", ("産科", "婦人科")) is None

    def test_more_keyword_hits_wins(self):
        text = "子宮筋腫による過多月経。妊娠の希望はない。"
        assert classify(text) == "婦人科"


class TestSortKey:
    def test_canonical_order_is_followed(self):
        names = ["公衆衛生", "循環器", "小児"]
        assert sorted(names, key=category_sort_key) == ["循環器", "小児", "公衆衛生"]

    def test_unknown_names_sort_last(self):
        names = ["謎の分野", "循環器"]
        assert sorted(names, key=category_sort_key) == ["循環器", "謎の分野"]


@pytest.mark.django_db
class TestReclassifyCommand:
    def test_renames_and_splits_existing_questions(self):
        from django.core.management import call_command

        common = dict(
            exam_type=Question.ExamType.CBT,
            choices=[{"key": "A", "text": "あ"}, {"key": "B", "text": "い"}],
            correct_choice_key="A",
            status=Question.Status.PUBLISHED,
        )
        renamed = Question.objects.create(
            category="呼吸器系", question_text="肺炎の起炎菌はどれか。", **common
        )
        obstetric = Question.objects.create(
            category="産婦人科系", question_text="妊娠高血圧症候群の管理はどれか。", **common
        )
        already = Question.objects.create(
            category="循環器", question_text="心不全の治療はどれか。", **common
        )

        call_command("reclassify_categories")

        renamed.refresh_from_db()
        obstetric.refresh_from_db()
        already.refresh_from_db()
        assert renamed.category == "呼吸器"
        assert obstetric.category == "産科"
        assert already.category == "循環器"

    def test_dry_run_changes_nothing(self):
        from django.core.management import call_command

        q = Question.objects.create(
            category="呼吸器系",
            question_text="肺炎の起炎菌はどれか。",
            exam_type=Question.ExamType.CBT,
            choices=[{"key": "A", "text": "あ"}, {"key": "B", "text": "い"}],
            correct_choice_key="A",
            status=Question.Status.PUBLISHED,
        )
        call_command("reclassify_categories", "--dry-run")
        q.refresh_from_db()
        assert q.category == "呼吸器系"
