import pytest
from django.utils import timezone

from battle.models import BattleRoom, BattleRound, MatchmakingTicket
from battle.scoring import round_time_limit_seconds
from quiz.models import AnswerHistory

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db


def make_room(n_questions=10, participants=2):
    """Create a room with N published questions and M participants.
    Returns (clients, profiles, room_code). clients[0] is the host."""
    for i in range(n_questions):
        make_question(question_text=f"バトル設問{i}", correct_choice_key="A")
    clients, profiles = [], []
    for _ in range(participants):
        client, profile = auth_client(display_name=f"P{len(clients) + 1}")
        clients.append(client)
        profiles.append(profile)

    res = clients[0].post("/api/battle/rooms/", {}, format="json")
    assert res.status_code in (201, 400)
    if res.status_code == 400:
        raise AssertionError(res.content)
    code = res.json()["room_code"]
    for client in clients[1:]:
        assert client.post(f"/api/battle/rooms/{code}/join/").status_code == 200
    return clients, profiles, code


def answer(client, round_id, key):
    return client.post(
        f"/api/battle/rounds/{round_id}/answer/",
        {"selected_choice_key": key},
        format="json",
    )


def current_round_id(client, code):
    return client.get(f"/api/battle/rooms/{code}/state/").json()["round"]["id"]


class TestBattleFlow:
    def test_correct_vs_wrong_deals_20_percent(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)

        assert answer(clients[0], round_id, "A").json()["correct"] is True
        assert answer(clients[1], round_id, "B").json()["correct"] is False

        room = BattleRoom.objects.get(room_code=code)
        assert room.participants.get(user=profiles[0]).hp == 100
        assert room.participants.get(user=profiles[1]).hp == 80

    def test_both_correct_damages_the_slower_by_10_percent(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)

        answer(clients[0], round_id, "A")  # 先に正解
        answer(clients[1], round_id, "A")  # あとから正解 → 10%被弾

        room = BattleRoom.objects.get(room_code=code)
        assert room.participants.get(user=profiles[0]).hp == 100
        assert room.participants.get(user=profiles[1]).hp == 90

    def test_both_wrong_deals_no_damage(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)

        answer(clients[0], round_id, "B")
        answer(clients[1], round_id, "C")

        room = BattleRoom.objects.get(room_code=code)
        assert room.participants.get(user=profiles[0]).hp == 100
        assert room.participants.get(user=profiles[1]).hp == 100

    def test_round_advances_only_after_both_answered(self):
        clients, _, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)

        answer(clients[0], round_id, "A")
        # まだ相手が答えていないので同じラウンドのまま
        state = clients[0].get(f"/api/battle/rooms/{code}/state/").json()
        assert state["round"]["id"] == round_id
        assert state["round"]["i_have_answered"] is True

        answer(clients[1], round_id, "A")
        state = clients[0].get(f"/api/battle/rooms/{code}/state/").json()
        assert state["round"]["number"] == 2

    def test_cannot_answer_twice(self):
        clients, _, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)
        assert answer(clients[0], round_id, "A").status_code == 200
        assert answer(clients[0], round_id, "B").status_code == 400

    def test_battle_ends_when_hp_reaches_zero(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        room = BattleRoom.objects.get(room_code=code)

        # 20%ダメージ×5回でHPが0になり、全10問を待たずに終了する。
        for _ in range(5):
            state = clients[0].get(f"/api/battle/rooms/{code}/state/").json()
            if state["room"]["status"] == "finished":
                break
            round_id = state["round"]["id"]
            answer(clients[0], round_id, "A")
            answer(clients[1], round_id, "B")

        room.refresh_from_db()
        assert room.participants.get(user=profiles[1]).hp == 0
        assert room.status == BattleRoom.Status.FINISHED

    def test_state_exposes_opponent_identity_for_the_vs_header(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        state = clients[0].get(f"/api/battle/rooms/{code}/state/").json()
        me = next(p for p in state["participants"] if p["is_me"])
        opponent = next(p for p in state["participants"] if not p["is_me"])
        for row in (me, opponent):
            assert "display_name" in row
            assert "university" in row
            assert "tier" in row
            assert row["hp"] == 100

    def test_answers_are_hidden_until_the_round_closes(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)
        answer(clients[0], round_id, "A")

        # 相手からは「答えたこと」だけ見え、選んだ選択肢は見えない。
        state = clients[1].get(f"/api/battle/rooms/{code}/state/").json()
        assert str(profiles[0].id) in state["round"]["answered_profile_ids"]
        assert state["round"]["i_have_answered"] is False
        assert "correct_choice_key" not in state["round"]["question"]

    def test_non_participant_cannot_see_state(self):
        clients, _, code = make_room()
        outsider, _ = auth_client(display_name="部外者")
        assert outsider.get(f"/api/battle/rooms/{code}/state/").status_code == 403


class TestRoundTimeout:
    def test_timeout_closes_round(self, monkeypatch):
        clients, _, code = make_room(participants=2)
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        room = BattleRoom.objects.get(room_code=code)
        round1 = room.rounds.get(round_number=1)
        # 出題時刻を31秒前に偽装 → 次の state ポーリングでクローズされる
        BattleRound.objects.filter(pk=round1.pk).update(
            revealed_at=round1.revealed_at
            - timezone_delta(round_time_limit_seconds(round1.question) + 1)
        )
        state = clients[0].get(f"/api/battle/rooms/{code}/state/").json()
        assert state["round"]["number"] == 2
        round1.refresh_from_db()
        assert round1.closed_at is not None


def timezone_delta(seconds):
    import datetime

    return datetime.timedelta(seconds=seconds)


class TestQuickMatch:
    def test_two_humans_are_matched_by_quickmatch(self):
        for i in range(10):
            make_question(question_text=f"QM設問{i}", correct_choice_key="A")
        c1, p1 = auth_client(display_name="アリス", grade=4)
        c2, p2 = auth_client(display_name="ボブ", grade=4)

        res1 = c1.post("/api/battle/quickmatch/", {}, format="json")
        assert res1.status_code == 201
        assert res1.json()["status"] == "waiting"
        ticket1_id = res1.json()["ticket_id"]

        res2 = c2.post("/api/battle/quickmatch/", {}, format="json")
        assert res2.json()["status"] == "matched"
        assert res2.json()["room_code"]
        assert res2.json()["opponent"]["display_name"] == "アリス"

        poll1 = c1.get(f"/api/battle/quickmatch/{ticket1_id}/").json()
        assert poll1["status"] == "matched"
        assert poll1["room_code"] == res2.json()["room_code"]
        assert poll1["opponent"]["display_name"] == "ボブ"

        room = BattleRoom.objects.get(room_code=poll1["room_code"])
        assert room.status == BattleRoom.Status.IN_PROGRESS
        assert room.participants.count() == 2

    def test_timeout_falls_back_to_ai_opponent(self):
        for i in range(10):
            make_question(question_text=f"AI設問{i}", correct_choice_key="A")
        client, profile = auth_client(display_name="ソロ待機", grade=4)
        ticket_id = client.post(
            "/api/battle/quickmatch/", {}, format="json"
        ).json()["ticket_id"]

        from battle.models import MatchmakingTicket

        MatchmakingTicket.objects.filter(pk=ticket_id).update(
            created_at=timezone.now() - timezone_delta(61)
        )

        poll = client.get(f"/api/battle/quickmatch/{ticket_id}/").json()
        assert poll["status"] == "ai_matched"
        # AIかどうかはクライアントに返さない（人間と見分けが付かないように）。
        assert "is_ai" not in poll["opponent"]
        room = BattleRoom.objects.get(room_code=poll["room_code"])
        assert room.participants.filter(user__is_ai=True).exists()

        # AIは人間側のポーリングのたびに1手ずつ進む。実運用は1.5秒間隔の
        # ポーリングで実時間が経過するが、テストでは連続で叩くため経過時間を
        # 作れない。ラウンドタイムアウト(30秒)を偽装して強制的に進行させる。
        # AIの正答率は確率的なので、HP切れではなく「全ラウンド消化」で必ず
        # 終わるよう、ラウンド数より十分多く回す。
        for _ in range(40):
            state = client.get(f"/api/battle/rooms/{room.room_code}/state/").json()
            if state["room"]["status"] == "finished":
                break
            open_round = room.rounds.filter(closed_at__isnull=True).order_by("round_number").first()
            if open_round and open_round.revealed_at:
                BattleRound.objects.filter(pk=open_round.pk).update(
                    revealed_at=timezone.now()
                    - timezone_delta(
                        round_time_limit_seconds(open_round.question) + 1
                    )
                )
        assert state["room"]["status"] == "finished"


class TestLeaveRoom:
    def test_leave_waiting_room_removes_participant(self):
        clients, profiles, code = make_room(participants=2)
        res = clients[1].post(f"/api/battle/rooms/{code}/leave/")
        assert res.status_code == 200
        room = BattleRoom.objects.get(room_code=code)
        assert room.participants.count() == 1
        assert not room.participants.filter(user=profiles[1]).exists()

    def test_host_leaving_waiting_room_hands_off_to_next_participant(self):
        clients, profiles, code = make_room(participants=2)
        res = clients[0].post(f"/api/battle/rooms/{code}/leave/")
        assert res.status_code == 200
        room = BattleRoom.objects.get(room_code=code)
        assert room.participants.count() == 1
        assert room.host_id == profiles[1].id

    def test_last_participant_leaving_waiting_room_deletes_it(self):
        clients, profiles, code = make_room(participants=2)
        clients[1].post(f"/api/battle/rooms/{code}/leave/")
        clients[0].post(f"/api/battle/rooms/{code}/leave/")
        assert not BattleRoom.objects.filter(room_code=code).exists()

    def test_leaving_in_progress_room_freezes_score_and_spawns_disguised_ai(self):
        clients, profiles, code = make_room(participants=2)
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        room = BattleRoom.objects.get(room_code=code)
        leaver = room.participants.get(user=profiles[1])
        leaver.score = 40
        leaver.save(update_fields=["score"])

        res = clients[1].post(f"/api/battle/rooms/{code}/leave/")
        assert res.status_code == 200

        leaver.refresh_from_db()
        assert leaver.left_at is not None
        assert leaver.score == 40  # 離脱時点で凍結され、以後増えない

        room.refresh_from_db()
        assert room.status == BattleRoom.Status.IN_PROGRESS  # もう1人は人間なので続行
        ai_participant = room.participants.get(user__is_ai=True)
        assert ai_participant.left_at is None
        # 「AI」だと分かる表示名や、固定の偽名を使い回していないことを確認する。
        assert "AI" not in ai_participant.user.display_name
        assert ai_participant.ai_tier

    def test_leaving_ai_only_room_finishes_immediately(self):
        for i in range(10):
            make_question(question_text=f"離脱設問{i}", correct_choice_key="A")
        client, profile = auth_client(display_name="ひとり", grade=4)
        ticket_id = client.post(
            "/api/battle/quickmatch/", {}, format="json"
        ).json()["ticket_id"]
        from battle.models import MatchmakingTicket

        MatchmakingTicket.objects.filter(pk=ticket_id).update(
            created_at=timezone.now() - timezone_delta(61)
        )
        poll = client.get(f"/api/battle/quickmatch/{ticket_id}/").json()
        code = poll["room_code"]

        res = client.post(f"/api/battle/rooms/{code}/leave/")
        assert res.status_code == 200
        room = BattleRoom.objects.get(room_code=code)
        assert room.status == BattleRoom.Status.FINISHED

    def test_cannot_leave_finished_room(self):
        clients, profiles, code = make_room(participants=2)
        room = BattleRoom.objects.get(room_code=code)
        room.status = BattleRoom.Status.FINISHED
        room.save(update_fields=["status"])
        res = clients[0].post(f"/api/battle/rooms/{code}/leave/")
        assert res.status_code == 400

    def test_disconnected_participant_is_auto_replaced_by_ai(self):
        clients, profiles, code = make_room(participants=2)
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        room = BattleRoom.objects.get(room_code=code)
        stale_participant = room.participants.get(user=profiles[1])
        stale_participant.last_seen_at = timezone.now() - timezone_delta(31)
        stale_participant.save(update_fields=["last_seen_at"])

        # もう一方の参加者がポーリングすることで、無応答側が自動的に入れ替わる。
        clients[0].get(f"/api/battle/rooms/{code}/state/")

        stale_participant.refresh_from_db()
        assert stale_participant.left_at is not None
        assert room.participants.filter(user__is_ai=True).exists()


class TestQuickMatchTicketReuse:
    def test_restarting_search_resets_the_elapsed_clock(self):
        """探索を途中でやめた後に押し直すと、経過時間が数え直される。

        WAITING のまま残ったチケットを使い回すと「経過1033秒」のように
        前回からの積算が表示され、押した瞬間にタイムアウト扱いにもなる。
        """
        for i in range(10):
            make_question(question_text=f"再探索設問{i}", correct_choice_key="A")
        client, profile = auth_client(display_name="やり直す人", grade=4)

        first = client.post("/api/battle/quickmatch/", {}, format="json").json()
        MatchmakingTicket.objects.filter(pk=first["ticket_id"]).update(
            created_at=timezone.now() - timezone_delta(1033)
        )

        again = client.post("/api/battle/quickmatch/", {}, format="json").json()
        assert again["ticket_id"] == first["ticket_id"]  # 同じチケットを使い回す
        assert again["status"] == "waiting"
        assert again["elapsed_seconds"] < 5  # 押し直した時点から数え直す


class TestAiAnswerTiming:
    def test_longer_questions_take_the_ai_longer(self):
        from battle.ai import _ai_target_delay

        short = make_question(question_text="短い問題。", correct_choice_key="A")
        long_stem = "７５歳男性。３日前からの発熱と咳嗽を主訴に来院した。" * 12
        long_q = make_question(question_text=long_stem, correct_choice_key="A")

        short_delay = _ai_target_delay("B", short, seed_key=(1, "x"))
        long_delay = _ai_target_delay("B", long_q, seed_key=(1, "x"))
        assert long_delay > short_delay

    def test_delay_is_stable_across_polls(self):
        """ポーリングのたびに引き直すと、狙いより早く答えてしまう。"""
        from battle.ai import _ai_target_delay

        q = make_question(question_text="安定性の確認。", correct_choice_key="A")
        first = _ai_target_delay("B", q, seed_key=(42, "abc"))
        for _ in range(20):
            assert _ai_target_delay("B", q, seed_key=(42, "abc")) == first

    def test_never_answers_instantly(self):
        from battle.ai import MIN_ANSWER_SECONDS, _ai_target_delay

        q = make_question(question_text="短", correct_choice_key="A")
        for tier in ("SS", "S", "A", "B", "C", "D"):
            for i in range(30):
                delay = _ai_target_delay(tier, q, seed_key=(i, tier))
                assert delay >= MIN_ANSWER_SECONDS

    def test_stronger_tiers_answer_sooner_on_the_same_question(self):
        from battle.ai import _ai_target_delay

        q = make_question(question_text="標準的な長さの問題文。" * 8, correct_choice_key="A")
        # ばらつきを同条件にするため seed を固定して比較する。
        ss = _ai_target_delay("SS", q, seed_key=(7, "same"))
        d = _ai_target_delay("D", q, seed_key=(7, "same"))
        assert ss < d


class TestRoundTimeLimit:
    def test_time_limit_is_a_flat_20_seconds(self):
        from battle.scoring import ROUND_TIME_LIMIT_SECONDS

        assert ROUND_TIME_LIMIT_SECONDS == 20
        huge = make_question(question_text="あ" * 5000, correct_choice_key="A")
        short = make_question(question_text="短", correct_choice_key="A")
        assert round_time_limit_seconds(huge) == 20
        assert round_time_limit_seconds(short) == 20

    def test_ai_answers_within_the_time_limit(self):
        """Dランクでも制限時間内に答え切れること（無回答が続くと対戦が進まない）。"""
        from battle.ai import _ai_target_delay

        long_q = make_question(
            question_text="７２歳男性。３日前からの発熱と湿性咳嗽を主訴に来院した。" * 8,
            correct_choice_key="A",
        )
        limit = round_time_limit_seconds(long_q)
        for i in range(50):
            assert _ai_target_delay("D", long_q, seed_key=(i, "d")) < limit


class TestAiDisplayName:
    """AIの表示名は「苗字だけ」「下の名前だけ」「ニックネーム」の3パターン。

    フルネーム（苗字＋名前）は実在の人物を指しているように見えるので使わない。
    """

    def test_never_generates_a_full_name(self):
        from battle.ai import _GIVEN_NAMES, _NICKNAMES, _SURNAMES, _random_display_name

        allowed = set(_SURNAMES) | set(_GIVEN_NAMES) | set(_NICKNAMES)
        names = {_random_display_name() for _ in range(300)}
        assert names <= allowed
        # 「佐藤 陽翔」のように連結された名前が出ていないこと。
        assert all(" " not in name for name in names)

    def test_uses_every_style(self):
        from battle.ai import _GIVEN_NAMES, _NICKNAMES, _SURNAMES, _random_display_name

        names = {_random_display_name() for _ in range(300)}
        assert names & set(_SURNAMES)
        assert names & set(_GIVEN_NAMES)
        assert names & set(_NICKNAMES)


class TestMatchTimeoutWindow:
    def test_timeout_falls_within_the_configured_window(self):
        from battle.matchmaking import (
            MATCH_TIMEOUT_MAX_SECONDS,
            MATCH_TIMEOUT_MIN_SECONDS,
            match_timeout_for,
        )

        class FakeTicket:
            def __init__(self, pk):
                self.pk = pk

        values = [match_timeout_for(FakeTicket(i)) for i in range(200)]
        assert all(MATCH_TIMEOUT_MIN_SECONDS <= v <= MATCH_TIMEOUT_MAX_SECONDS for v in values)
        # チケットごとにばらついている（毎回同じ秒数だと機械的に見える）
        assert len(set(round(v, 2) for v in values)) > 100

    def test_timeout_is_stable_for_the_same_ticket(self):
        """ポーリングのたびに引き直すと、実質いちばん短い値で固定されてしまう。"""
        from battle.matchmaking import match_timeout_for

        class FakeTicket:
            pk = 4242

        first = match_timeout_for(FakeTicket())
        for _ in range(30):
            assert match_timeout_for(FakeTicket()) == first

    def test_ai_fallback_does_not_fire_before_the_window(self):
        for i in range(10):
            make_question(question_text=f"待機設問{i}", correct_choice_key="A")
        client, _ = auth_client(display_name="待つ人", grade=4)
        ticket_id = client.post("/api/battle/quickmatch/", {}, format="json").json()["ticket_id"]
        from battle.matchmaking import (
            MATCH_TIMEOUT_MAX_SECONDS,
            MATCH_TIMEOUT_MIN_SECONDS,
        )

        # 下限（10秒）より手前ではまだ切り替わらない
        MatchmakingTicket.objects.filter(pk=ticket_id).update(
            created_at=timezone.now() - timezone_delta(MATCH_TIMEOUT_MIN_SECONDS - 1)
        )
        assert client.get(f"/api/battle/quickmatch/{ticket_id}/").json()["status"] == "waiting"

        # 上限（25秒）を過ぎれば必ず切り替わる
        MatchmakingTicket.objects.filter(pk=ticket_id).update(
            created_at=timezone.now() - timezone_delta(MATCH_TIMEOUT_MAX_SECONDS + 1)
        )
        assert client.get(f"/api/battle/quickmatch/{ticket_id}/").json()["status"] == "ai_matched"


class TestUnansweredCountsAsWrong:
    def test_not_answering_takes_the_same_damage_as_a_wrong_answer(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        room = BattleRoom.objects.get(room_code=code)
        round_id = current_round_id(clients[0], code)

        answer(clients[0], round_id, "A")  # 正解
        # clients[1] は答えないまま時間切れにする
        BattleRound.objects.filter(pk=round_id).update(
            revealed_at=timezone.now() - timezone_delta(round_time_limit_seconds(None) + 1)
        )
        clients[0].get(f"/api/battle/rooms/{code}/state/")

        assert room.participants.get(user=profiles[0]).hp == 100
        assert room.participants.get(user=profiles[1]).hp == 80  # 不正解と同じ20%


class TestAiRespondsAfterOpponent:
    def test_ai_answers_within_two_seconds_of_the_opponent(self):
        """相手が答えたのに待たされ続けないこと。"""
        import datetime

        from battle.ai import ANSWER_AFTER_OPPONENT_SECONDS, simulate_ai_turn
        from battle.matchmaking import MatchmakingTicket

        for i in range(10):
            make_question(question_text=f"AI応答設問{i}" * 30, correct_choice_key="A")
        client, profile = auth_client(display_name="人間", grade=4)
        ticket_id = client.post("/api/battle/quickmatch/", {}, format="json").json()["ticket_id"]
        MatchmakingTicket.objects.filter(pk=ticket_id).update(
            created_at=timezone.now() - timezone_delta(41)
        )
        code = client.get(f"/api/battle/quickmatch/{ticket_id}/").json()["room_code"]
        room = BattleRoom.objects.get(room_code=code)

        round_id = current_round_id(client, code)
        answer(client, round_id, "A")

        round_ = BattleRound.objects.get(pk=round_id)
        if round_.closed_at is not None:
            return  # AIが先に答えて決着済みなら、この検証の対象外

        # 相手（人間）の回答から2秒より前ではAIはまだ答えない
        simulate_ai_turn(room)
        assert not round_.buzzes.filter(profile__is_ai=True).exists()

        # 「人間の回答から2秒経過」を作る。revealed_at をずらしても
        # 経過時間と相手の回答時刻が同じだけ動いて差が変わらないので、
        # 相手の回答時刻そのものを巻き戻す。
        from battle.models import BattleBuzz

        BattleBuzz.objects.filter(round_id=round_id, profile=profile).update(
            buzzed_at=timezone.now()
            - datetime.timedelta(seconds=ANSWER_AFTER_OPPONENT_SECONDS + 0.5)
        )
        room.refresh_from_db()
        simulate_ai_turn(room)
        assert BattleRound.objects.get(pk=round_id).buzzes.filter(profile__is_ai=True).exists()


class TestLeavePenalty:
    def test_leaving_mid_battle_costs_rank_points(self):
        from accounts.ranktier import LEAVE_PENALTY_POINTS

        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        leaver = profiles[1]
        leaver.points = 250
        leaver.ranked_matches = 5
        leaver.save(update_fields=["points", "ranked_matches"])

        clients[1].post(f"/api/battle/rooms/{code}/leave/")

        leaver.refresh_from_db()
        assert leaver.points == 250 - LEAVE_PENALTY_POINTS
        # 対戦を1回こなしたわけではないので対戦回数は増やさない
        assert leaver.ranked_matches == 5

    def test_leaving_while_waiting_has_no_penalty(self):
        clients, profiles, code = make_room()
        leaver = profiles[1]
        leaver.points = 250
        leaver.save(update_fields=["points"])

        clients[1].post(f"/api/battle/rooms/{code}/leave/")

        leaver.refresh_from_db()
        assert leaver.points == 250

    def test_penalty_never_pushes_points_below_zero(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        leaver = profiles[1]
        leaver.points = 3
        leaver.save(update_fields=["points"])

        clients[1].post(f"/api/battle/rooms/{code}/leave/")

        leaver.refresh_from_db()
        assert leaver.points == 0

    def test_dropping_out_silently_is_penalised_too(self):
        """タブを閉じるだけでペナルティを回避できないこと。"""
        from accounts.ranktier import LEAVE_PENALTY_POINTS

        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        room = BattleRoom.objects.get(room_code=code)
        stale = room.participants.get(user=profiles[1])
        stale.last_seen_at = timezone.now() - timezone_delta(31)
        stale.save(update_fields=["last_seen_at"])
        profiles[1].points = 250
        profiles[1].save(update_fields=["points"])

        clients[0].get(f"/api/battle/rooms/{code}/state/")

        profiles[1].refresh_from_db()
        assert profiles[1].points == 250 - LEAVE_PENALTY_POINTS


class TestResultQuestionReview:
    """対戦後に「出た問題」と自分の正誤・解説を返すこと。"""

    def test_result_lists_each_question_with_my_verdict_and_explanation(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")

        round_id = current_round_id(clients[0], code)
        answer(clients[0], round_id, "A")  # 正解
        answer(clients[1], round_id, "B")  # 不正解
        round_id = current_round_id(clients[0], code)
        answer(clients[0], round_id, "B")  # 不正解
        answer(clients[1], round_id, "A")  # 正解

        rows = clients[0].get(f"/api/battle/rooms/{code}/result/").json()["questions"]

        # 出題済みのラウンドだけ（=解答した2問）が、出題順で並ぶ
        assert [r["round_number"] for r in rows] == [1, 2]
        assert [r["correct"] for r in rows] == [True, False]
        assert [r["selected_choice_key"] for r in rows] == ["A", "B"]
        assert all(r["answered"] for r in rows)
        # 解説と正解キーは対戦が終わってから読めるようになる
        assert all(r["explanation"] and r["correct_choice_key"] == "A" for r in rows)
        assert all(r["question_text"].startswith("バトル設問") for r in rows)
        assert all(len(r["choices"]) >= 2 for r in rows)

        # 相手には相手自身の正誤が返る
        opponent_rows = clients[1].get(f"/api/battle/rooms/{code}/result/").json()["questions"]
        assert [r["correct"] for r in opponent_rows] == [False, True]

    def test_unanswered_question_is_marked_as_unanswered_not_wrong(self):
        clients, profiles, code = make_room()
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = current_round_id(clients[0], code)

        answer(clients[0], round_id, "A")
        # clients[1] は答えないまま時間切れ
        BattleRound.objects.filter(pk=round_id).update(
            revealed_at=timezone.now() - timezone_delta(round_time_limit_seconds(None) + 1)
        )
        clients[1].get(f"/api/battle/rooms/{code}/state/")

        row = clients[1].get(f"/api/battle/rooms/{code}/result/").json()["questions"][0]
        assert row["answered"] is False
        assert row["correct"] is False
        assert row["selected_choice_key"] is None


class TestRoomHoldsTwoPlayers:
    """対戦ルームは1対1。HPの削り合いが2人を前提にした計算なので、
    3人目は入れない。"""

    def test_a_third_player_cannot_join(self):
        clients, _, code = make_room(participants=2)
        third, _ = auth_client(display_name="3人目")

        res = third.post(f"/api/battle/rooms/{code}/join/")

        assert res.status_code == 400
        assert "2人" in res.content.decode()
        assert BattleRoom.objects.get(room_code=code).participants.count() == 2

    def test_rejoining_still_works_for_someone_already_in(self):
        """満室でも、すでに入っている人の再入室は通ること（冪等）。"""
        clients, _, code = make_room(participants=2)
        assert clients[1].post(f"/api/battle/rooms/{code}/join/").status_code == 200
        assert BattleRoom.objects.get(room_code=code).participants.count() == 2

    def test_a_freed_slot_can_be_taken(self):
        clients, _, code = make_room(participants=2)
        clients[1].post(f"/api/battle/rooms/{code}/leave/")
        third, _ = auth_client(display_name="3人目")

        assert third.post(f"/api/battle/rooms/{code}/join/").status_code == 200
        assert BattleRoom.objects.get(room_code=code).participants.count() == 2
