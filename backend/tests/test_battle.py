import threading
import uuid
from pathlib import Path

import pytest
from django.db import connection, connections
from django.utils import timezone

from accounts.models import Profile
from battle.models import BattleBuzz, BattleRoom, BattleRound
from battle.scoring import CORRECT_POINTS, FIRST_BUZZ_BONUS, WRONG_PENALTY
from exams.management.commands.aggregate_rankings import fetch_user_stats
from quiz.models import AnswerHistory

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db

CLAIM_BUZZ_SQL = (
    Path(__file__).resolve().parent.parent.parent
    / "supabase"
    / "migrations"
    / "20260723002000_claim_buzz.sql"
)


def make_room(n_questions=3, participants=2):
    """Create a room with N published questions and M participants.
    Returns (clients, profiles, room_code). clients[0] is the host."""
    for i in range(n_questions):
        make_question(question_text=f"バトル設問{i}", correct_choice_key="A")
    clients, profiles = [], []
    for _ in range(participants):
        client, profile = auth_client(display_name=f"P{len(clients) + 1}")
        clients.append(client)
        profiles.append(profile)

    res = clients[0].post(
        "/api/battle/rooms/", {"question_count": 5}, format="json"
    )
    # 5問未満しかない場合に備えテストは question_count=5 で作らない
    assert res.status_code in (201, 400)
    if res.status_code == 400:
        raise AssertionError(res.content)
    code = res.json()["room_code"]
    for client in clients[1:]:
        assert client.post(f"/api/battle/rooms/{code}/join/").status_code == 200
    return clients, profiles, code


class TestBattleFlow:
    def test_full_match_flow(self):
        # 5問 published を用意
        for i in range(5):
            make_question(question_text=f"設問{i}", correct_choice_key="A")
        host, host_profile = auth_client(display_name="ホスト")
        guest, guest_profile = auth_client(display_name="ゲスト")

        code = host.post(
            "/api/battle/rooms/", {"question_count": 5}, format="json"
        ).json()["room_code"]
        assert guest.post(f"/api/battle/rooms/{code}/join/").status_code == 200

        # ホスト以外は開始できない
        assert guest.post(f"/api/battle/rooms/{code}/start/").status_code == 403
        assert host.post(f"/api/battle/rooms/{code}/start/").status_code == 200

        room = BattleRoom.objects.get(room_code=code)
        assert room.rounds.count() == 5  # 全ラウンドを先に作成 (spec 4-2)
        state = host.get(f"/api/battle/rooms/{code}/state/").json()
        assert state["round"]["number"] == 1
        assert "correct_choice_key" not in state["round"]["question"]

        round_id = state["round"]["id"]
        # guest が先に早押し → rank 1、host は rank 2
        assert guest.post(f"/api/battle/rounds/{round_id}/buzz/").json()["rank"] == 1
        assert host.post(f"/api/battle/rounds/{round_id}/buzz/").json()["rank"] == 2

        # host は回答権なし（rank2, rank1未回答）
        res = host.post(
            f"/api/battle/rounds/{round_id}/answer/",
            {"selected_choice_key": "A"},
            format="json",
        )
        assert res.status_code == 403

        # guest 誤答 → -30（下限0）→ 回答権が host に移る
        res = guest.post(
            f"/api/battle/rounds/{round_id}/answer/",
            {"selected_choice_key": "B"},
            format="json",
        )
        assert res.json()["correct"] is False
        assert res.json()["score"] == 0  # max(0, 0-30)

        # host 正解 → +100（rank2 なのでボーナスなし）→ ラウンドが閉じ次へ
        res = host.post(
            f"/api/battle/rounds/{round_id}/answer/",
            {"selected_choice_key": "A"},
            format="json",
        )
        assert res.json()["correct"] is True
        assert res.json()["score"] == CORRECT_POINTS

        state = host.get(f"/api/battle/rooms/{code}/state/").json()
        assert state["round"]["number"] == 2
        assert state["last_result"]["correct_choice_key"] == "A"

        # 対戦の解答は AnswerHistory に context=battle で記録される (spec 4-2)
        assert AnswerHistory.objects.filter(
            user=guest_profile, context="battle", correct=False
        ).exists()
        # …がランキング集計には含まれない
        assert guest_profile.id not in fetch_user_stats("all")

    def test_two_clients_complete_all_rounds(self):
        """2クライアントで全ラウンド完走 → finished + 結果表示 (完了条件)."""
        for i in range(5):
            make_question(question_text=f"完走設問{i}", correct_choice_key="A")
        host, _ = auth_client(display_name="勝者")
        guest, _ = auth_client(display_name="敗者")
        code = host.post(
            "/api/battle/rooms/", {"question_count": 5}, format="json"
        ).json()["room_code"]
        guest.post(f"/api/battle/rooms/{code}/join/")
        host.post(f"/api/battle/rooms/{code}/start/")

        for _ in range(5):
            state = host.get(f"/api/battle/rooms/{code}/state/").json()
            round_id = state["round"]["id"]
            host.post(f"/api/battle/rounds/{round_id}/buzz/")
            host.post(
                f"/api/battle/rounds/{round_id}/answer/",
                {"selected_choice_key": "A"},
                format="json",
            )

        state = host.get(f"/api/battle/rooms/{code}/state/").json()
        assert state["room"]["status"] == "finished"

        result = guest.get(f"/api/battle/rooms/{code}/result/").json()
        assert result["standings"][0]["display_name"] == "勝者"
        assert result["standings"][0]["rank"] == 1
        assert result["standings"][0]["correct_count"] == 5
        assert result["standings"][0]["score"] == 5 * (CORRECT_POINTS + FIRST_BUZZ_BONUS)
        assert result["standings"][1]["rank"] == 2

        # 対戦ランクポイント (spec: 対戦＋模試の合算ポイントでSS〜Dランク) が
        # ルーム終了時に一度だけ確定し、勝者が敗者より多くもらう。
        assert result["standings"][0]["points_delta"] == 25  # 1位（2人中）
        assert result["standings"][1]["points_delta"] == -15  # 最下位
        host_profile = Profile.objects.get(display_name="勝者")
        guest_profile = Profile.objects.get(display_name="敗者")
        assert host_profile.points == 1025
        assert guest_profile.points == 985
        assert host_profile.ranked_matches == 1
        assert guest_profile.ranked_matches == 1

    def test_first_buzz_bonus(self):
        for i in range(5):
            make_question(question_text=f"B設問{i}", correct_choice_key="A")
        host, _ = auth_client(display_name="H")
        guest, _ = auth_client(display_name="G")
        code = host.post(
            "/api/battle/rooms/", {"question_count": 5}, format="json"
        ).json()["room_code"]
        guest.post(f"/api/battle/rooms/{code}/join/")
        host.post(f"/api/battle/rooms/{code}/start/")
        round_id = host.get(f"/api/battle/rooms/{code}/state/").json()["round"]["id"]

        host.post(f"/api/battle/rounds/{round_id}/buzz/")
        res = host.post(
            f"/api/battle/rounds/{round_id}/answer/",
            {"selected_choice_key": "A"},
            format="json",
        )
        assert res.json()["score"] == CORRECT_POINTS + FIRST_BUZZ_BONUS

    def test_non_participant_cannot_see_state(self):
        for i in range(5):
            make_question(question_text=f"C設問{i}")
        host, _ = auth_client()
        guest, _ = auth_client()
        outsider, _ = auth_client()
        code = host.post(
            "/api/battle/rooms/", {"question_count": 5}, format="json"
        ).json()["room_code"]
        guest.post(f"/api/battle/rooms/{code}/join/")
        assert outsider.get(f"/api/battle/rooms/{code}/state/").status_code == 403

    def test_score_floor_and_penalty(self):
        assert max(0, 50 - WRONG_PENALTY) == 20


@pytest.mark.django_db(transaction=True)
class TestBuzzRace:
    """同時押しで1人だけが rank=1 を得ることの検証 (spec 4-2 / 6)."""

    def _run_threads(self, worker, count):
        barrier = threading.Barrier(count)
        results, errors = [], []

        def wrapped(i):
            try:
                barrier.wait(timeout=10)
                results.append(worker(i))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                for conn in connections.all():
                    conn.close()

        threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not errors, errors
        return results

    def test_django_fallback_assigns_unique_ranks(self):
        clients, _, code = make_room(n_questions=5, participants=4)
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = clients[0].get(f"/api/battle/rooms/{code}/state/").json()["round"]["id"]

        ranks = self._run_threads(
            lambda i: clients[i].post(f"/api/battle/rounds/{round_id}/buzz/").json()["rank"],
            len(clients),
        )
        assert sorted(ranks) == [1, 2, 3, 4]  # 全員押せて、1位は1人だけ

    def test_claim_buzz_rpc_assigns_unique_ranks(self):
        """Supabase RPC を実 SQL としてテスト DB に適用し、並行実行する。

        auth.uid() は Supabase 互換のスタブ（request.jwt.claim.sub を返す）
        で差し替える。role 付与はテスト用クラスタに存在しないためスキップ。
        """
        clients, profiles, code = make_room(n_questions=5, participants=4)
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = clients[0].get(f"/api/battle/rooms/{code}/state/").json()["round"]["id"]

        sql = CLAIM_BUZZ_SQL.read_text(encoding="utf-8")
        sql = sql.split("revoke all")[0]  # grant/revoke は roles 不在のため除外
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS auth")
            cursor.execute(
                """
                CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
                LANGUAGE sql STABLE AS
                $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$
                """
            )
            cursor.execute(sql)

        def claim(i):
            conn = connections.create_connection("default")
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('request.jwt.claim.sub', %s, false)",
                        [str(profiles[i].id)],
                    )
                    cursor.execute("SELECT * FROM claim_buzz(%s)", [round_id])
                    return cursor.fetchone()[1]  # buzz_rank
            finally:
                conn.close()

        ranks = self._run_threads(claim, len(profiles))
        assert sorted(ranks) == [1, 2, 3, 4]
        assert BattleBuzz.objects.filter(round_id=round_id, rank=1).count() == 1

        # 二重押しは既存 rank を返す（冪等）
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('request.jwt.claim.sub', %s, false)",
                [str(profiles[0].id)],
            )
            cursor.execute("SELECT * FROM claim_buzz(%s)", [round_id])
            again = cursor.fetchone()[1]
        first = BattleBuzz.objects.get(round_id=round_id, profile=profiles[0]).rank
        assert again == first

    def test_rpc_rejects_non_participant(self):
        clients, profiles, code = make_room(n_questions=5, participants=2)
        clients[0].post(f"/api/battle/rooms/{code}/start/")
        round_id = clients[0].get(f"/api/battle/rooms/{code}/state/").json()["round"]["id"]

        sql = CLAIM_BUZZ_SQL.read_text(encoding="utf-8").split("revoke all")[0]
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS auth")
            cursor.execute(
                """
                CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
                LANGUAGE sql STABLE AS
                $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$
                """
            )
            cursor.execute(sql)

        outsider = uuid.uuid4()
        conn = connections.create_connection("default")
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('request.jwt.claim.sub', %s, false)", [str(outsider)]
                )
                with pytest.raises(Exception, match="not a participant"):
                    cursor.execute("SELECT * FROM claim_buzz(%s)", [round_id])
        finally:
            conn.close()

        # 部外者の行は作られていない
        assert not BattleBuzz.objects.filter(profile_id=outsider).exists()


class TestRoundTimeout:
    def test_timeout_closes_round(self, monkeypatch):
        clients, _, code = make_room(n_questions=5, participants=2)
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
        for i in range(5):
            make_question(question_text=f"QM設問{i}", correct_choice_key="A")
        c1, p1 = auth_client(display_name="アリス", grade=4)
        c2, p2 = auth_client(display_name="ボブ", grade=4)

        res1 = c1.post("/api/battle/quickmatch/", {"question_count": 5}, format="json")
        assert res1.status_code == 201
        assert res1.json()["status"] == "waiting"
        ticket1_id = res1.json()["ticket_id"]

        res2 = c2.post("/api/battle/quickmatch/", {"question_count": 5}, format="json")
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
        for i in range(5):
            make_question(question_text=f"AI設問{i}", correct_choice_key="A")
        client, profile = auth_client(display_name="ソロ待機", grade=4)
        ticket_id = client.post(
            "/api/battle/quickmatch/", {"question_count": 5}, format="json"
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

        # AIは人間側のポーリングのたびに1手ずつ進む（早押し→次のポーリングで解答）。
        # 実運用は1.5秒間隔のポーリングで実時間が経過するが、テストでは連続で
        # 叩くため経過時間を作れない。ラウンドタイムアウト(30秒)を偽装して
        # 強制的に進行させる（AIの正誤に関わらず、いずれこの経路でも閉じる）。
        for _ in range(10):
            state = client.get(f"/api/battle/rooms/{room.room_code}/state/").json()
            if state["room"]["status"] == "finished":
                break
            open_round = room.rounds.filter(closed_at__isnull=True).order_by("round_number").first()
            if open_round and open_round.revealed_at:
                BattleRound.objects.filter(pk=open_round.pk).update(
                    revealed_at=timezone.now() - timezone_delta(31)
                )
        assert state["room"]["status"] == "finished"
