"""分野名（category）の統制のテスト。

category は自由入力の CharField で、値を入れる経路が独立に4つあった
ため「循環器」と「循環器系」、「消化器」と「消化器系」のように同じ
分野が別名で並存していた。正典（quiz/categories.py）に寄せたので、
戻らないようにここで固定する。
"""

import json
from pathlib import Path

import pytest

from accounts.models import Profile
from quiz.categories import (
    CANONICAL_CATEGORIES,
    CATEGORY_ALIASES,
    canonicalize,
    is_canonical,
)

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db

DATA = Path(__file__).resolve().parents[1] / "quiz" / "management" / "commands" / "data"
AUTHORED = Path(__file__).resolve().parents[2] / "scripts" / "authored_content"


class TestCanon:
    def test_aliases_all_point_at_a_canonical_name(self):
        for alias, target in CATEGORY_ALIASES.items():
            assert is_canonical(target), f"{alias} -> {target} は正典に無い"

    def test_alias_is_not_also_canonical(self):
        # 別名が正典にも入っていると、寄せたつもりで両方生き残る
        for alias in CATEGORY_ALIASES:
            assert not is_canonical(alias), f"{alias} が別名かつ正典になっている"

    def test_canonicalize_fixes_the_observed_duplicates(self):
        assert canonicalize("循環器") == "循環器系"
        assert canonicalize("消化器") == "消化器系"
        assert canonicalize("呼吸器") == "呼吸器系"
        assert canonicalize("血液・造血器系") == "血液・造血器・リンパ系"
        assert canonicalize("救急・中毒") == "救急系"

    def test_canonical_names_pass_through_unchanged(self):
        for name in CANONICAL_CATEGORIES:
            assert canonicalize(name) == name


class TestBundledDataUsesCanonicalCategories:
    """同梱データに正典外の分野名が混ざっていないこと。"""

    def _categories_in(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {it.get("area_title", "") for it in data}
        names = {q["category"] for q in data.get("questions", [])}
        names |= {s["category"] for s in data.get("question_sets", [])}
        return names

    @pytest.mark.parametrize(
        "name",
        [p.name for p in sorted(DATA.glob("*.json")) if not p.name.endswith(".report.json")],
    )
    def test_batch_file(self, name):
        bad = {c for c in self._categories_in(DATA / name) if c and not is_canonical(c)}
        assert not bad, f"{name}: 正典外の分野 {bad}"

    def test_authored_content(self):
        bad = {}
        for p in sorted(AUTHORED.glob("*.json")):
            names = {c for c in self._categories_in(p) if c and not is_canonical(c)}
            if names:
                bad[p.name] = names
        assert not bad, f"正典外の分野 {bad}"


class TestAdminApiEnforcesCanon:
    payload = {
        "exam_type": "CBT",
        "difficulty": 2,
        "question_text": "分野の検証テスト用の設問",
        "choices": [{"key": k, "text": f"選択肢{k}"} for k in "ABCDE"],
        "correct_choice_key": "A",
        "explanation": "解説",
        "status": "pending",
    }

    def test_canonical_category_is_accepted(self):
        client, _ = auth_client(role=Profile.Role.ADMIN)
        res = client.post(
            "/api/admin/questions/", {**self.payload, "category": "循環器系"}, format="json"
        )
        assert res.status_code == 201, res.json()

    def test_alias_is_rejected_with_the_correct_name(self):
        client, _ = auth_client(role=Profile.Role.ADMIN)
        res = client.post(
            "/api/admin/questions/", {**self.payload, "category": "循環器"}, format="json"
        )
        assert res.status_code == 400
        assert "循環器系" in str(res.json()["category"])

    def test_unknown_category_is_rejected(self):
        client, _ = auth_client(role=Profile.Role.ADMIN)
        res = client.post(
            "/api/admin/questions/", {**self.payload, "category": "でたらめ分野"}, format="json"
        )
        assert res.status_code == 400

    def test_stats_exposes_the_canon_for_the_dropdown(self):
        client, _ = auth_client(role=Profile.Role.ADMIN)
        make_question(category="循環器系")
        body = client.get("/api/admin/stats/").json()
        assert body["canonical_categories"] == list(CANONICAL_CATEGORIES)
