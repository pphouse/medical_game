import pytest
from django.utils import timezone

from battle.models import BattleRoom, BattleRound
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
            revealed_at=round1.revealed_at - timezone_delta(31)
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
        assert poll["opponent"]["is_ai"] is True
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
                    revealed_at=timezone.now() - timezone_delta(31)
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
        clients, profiles, code = make_room(participants=3)
        res = clients[0].post(f"/api/battle/rooms/{code}/leave/")
        assert res.status_code == 200
        room = BattleRoom.objects.get(room_code=code)
        assert room.participants.count() == 2
        assert room.host_id in (profiles[1].id, profiles[2].id)

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
