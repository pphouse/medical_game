"""ランクの絶対ラダー（D→C→B→A→S→SS）と、対戦のポイント増減。"""

import random

import pytest

from accounts.ranktier import (
    MAX_TIER_INDEX,
    POINTS_PER_TIER,
    RANK_TIERS,
    battle_points_delta,
    progress_for_points,
    rank_state,
    tier_for_points,
)

from .helpers import auth_client

pytestmark = pytest.mark.django_db


class TestLadder:
    def test_points_map_to_tiers_every_100(self):
        assert tier_for_points(0) == "D"
        assert tier_for_points(99) == "D"
        assert tier_for_points(100) == "C"
        assert tier_for_points(250) == "B"
        assert tier_for_points(399) == "A"
        assert tier_for_points(400) == "S"
        assert tier_for_points(500) == "SS"
        assert tier_for_points(9999) == "SS"  # 最上位で頭打ち

    def test_progress_resets_to_zero_on_promotion(self):
        assert progress_for_points(99) == 99
        assert progress_for_points(100) == 0  # 昇格した瞬間は0%から
        assert progress_for_points(150) == 50

    def test_top_tier_progress_is_full(self):
        assert progress_for_points(500) == 100
        assert progress_for_points(1200) == 100

    def test_negative_points_are_floored_at_d_zero(self):
        assert tier_for_points(-50) == "D"
        assert progress_for_points(-50) == 0


class TestBattleDelta:
    def test_winning_by_a_bigger_margin_gains_more(self):
        close = battle_points_delta(my_hp=100, opponent_hp=90, current_points=0)
        blowout = battle_points_delta(my_hp=100, opponent_hp=0, current_points=0)
        assert 0 < close < blowout

    def test_losing_by_a_bigger_margin_costs_more(self):
        close = battle_points_delta(my_hp=90, opponent_hp=100, current_points=0)
        blowout = battle_points_delta(my_hp=0, opponent_hp=100, current_points=0)
        assert blowout < close < 0

    def test_draw_gives_nothing(self):
        assert battle_points_delta(my_hp=60, opponent_hp=60, current_points=0) == 0

    def test_higher_tiers_gain_less_for_the_same_win(self):
        gains = [
            battle_points_delta(my_hp=100, opponent_hp=50, current_points=p)
            for p in (0, 100, 200, 300, 400)
        ]
        assert gains == sorted(gains, reverse=True)
        assert gains[0] > gains[-1]

    def test_a_win_always_gains_at_least_one_point(self):
        """ランク補正で0に丸められて「勝ったのに増えない」ことがないように。"""
        for points in range(0, 600, 50):
            assert battle_points_delta(my_hp=51, opponent_hp=50, current_points=points) >= 1

    def test_reaching_the_top_tier_takes_over_100_battles(self):
        """勝率7割・平均点差50%で、SS到達までおおよそ100戦以上かかる設定。"""
        random.seed(20260825)
        runs = []
        for _ in range(200):
            points, battles = 0, 0
            while points < POINTS_PER_TIER * MAX_TIER_INDEX and battles < 5000:
                won = random.random() < 0.7
                margin = random.randint(10, 90)
                my_hp, opp_hp = (100, 100 - margin) if won else (100 - margin, 100)
                points = max(
                    0,
                    points
                    + battle_points_delta(
                        my_hp=my_hp, opponent_hp=opp_hp, current_points=points
                    ),
                )
                battles += 1
            runs.append(battles)
        runs.sort()
        median = runs[len(runs) // 2]
        assert 100 <= median <= 200, f"中央値 {median} 戦"


class TestRankState:
    def test_unranked_profile_has_no_tier(self):
        _, profile = auth_client()
        state = rank_state(profile)
        assert state["tier"] is None
        assert state["next_tier"] == RANK_TIERS[0]

    def test_ranked_profile_reports_tier_and_progress(self):
        _, profile = auth_client()
        profile.ranked_matches = 3
        profile.points = 240
        profile.save(update_fields=["ranked_matches", "points"])

        state = rank_state(profile)
        assert state["tier"] == "B"
        assert state["progress"] == 40
        assert state["next_tier"] == "A"

    def test_top_tier_has_no_next_tier(self):
        _, profile = auth_client()
        profile.ranked_matches = 1
        profile.points = 800
        profile.save(update_fields=["ranked_matches", "points"])
        assert rank_state(profile)["next_tier"] is None


class TestUniversityOrdering:
    def test_universities_are_listed_in_kana_order(self):
        """選択リストは五十音順（漢字のコード順ではなく読み順）。"""
        from accounts.models import University

        University.objects.create(name="北海道大学", name_kana="ほっかいどうだいがく")
        University.objects.create(name="愛知医科大学", name_kana="あいちいかだいがく")
        University.objects.create(name="京都大学", name_kana="きょうとだいがく")

        client, _ = auth_client()
        names = [u["name"] for u in client.get("/api/auth/universities/").json()]
        assert names == ["愛知医科大学", "京都大学", "北海道大学"]
