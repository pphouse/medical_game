import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { supabase } from "../../lib/supabase";
import Match from "./Match";
import Result from "./Result";

const POLL_INTERVAL_MS = 1500;

/** ルーム画面のコントローラ。state をポーリング（Supabase Realtime が
 * 設定されていれば battle テーブルの変更購読で即時リフレッシュ）し、
 * status に応じて 待機室 / 対戦 / 結果 を描画する。 */
export default function Room() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const stateRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.battleState(code);
      stateRef.current = next;
      setState(next);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [code]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_INTERVAL_MS);

    // Realtime 購読（設定時のみ）: 変更を検知したら即座に再フェッチ
    let channel = null;
    if (supabase) {
      channel = supabase
        .channel(`battle-${code}`)
        .on(
          "postgres_changes",
          { event: "*", schema: "public", table: "battle_battleround" },
          refresh
        )
        .on(
          "postgres_changes",
          { event: "*", schema: "public", table: "battle_battlebuzz" },
          refresh
        )
        .subscribe();
    }
    return () => {
      clearInterval(timer);
      if (channel) supabase.removeChannel(channel);
    };
  }, [code, refresh]);

  if (error) {
    return (
      <div className="screen">
        <button className="back-link" onClick={() => navigate("/battle")}>
          ← 対戦ロビーへ
        </button>
        <p className="error">{error}</p>
      </div>
    );
  }
  if (!state) {
    return (
      <div className="screen">
        <p>読み込み中...</p>
      </div>
    );
  }

  const { room, participants } = state;

  if (room.status === "finished") {
    return <Result code={code} />;
  }

  if (room.status === "in_progress") {
    return <Match state={state} refresh={refresh} />;
  }

  const me = participants.find((p) => p.is_me);
  return (
    <div className="screen">
      <button className="back-link" onClick={() => navigate("/battle")}>
        ← 対戦ロビーへ
      </button>
      <h2>対戦ルーム</h2>
      <div className="mypage-card battle-card">
        <p className="battle-room-code-label">ルームコード</p>
        <p className="battle-room-code">{room.room_code}</p>
        <p className="battle-room-hint">
          このコード（またはこのページの URL）を友だちに共有してください。
          {room.question_count}問勝負です。
        </p>
      </div>

      <div className="mypage-card battle-card">
        <h3 className="battle-card-title">参加者（{participants.length}人）</h3>
        {participants.map((p) => (
          <div key={p.display_name} className="battle-participant-row">
            <span>
              {p.display_name}
              {p.is_host && " 👑"}
              {p.is_me && "（あなた）"}
            </span>
            <span className={p.connected ? "battle-online" : "battle-offline"}>
              {p.connected ? "オンライン" : "オフライン"}
            </span>
          </div>
        ))}
      </div>

      {me?.is_host ? (
        <button
          className="cta-button"
          disabled={participants.length < 2}
          onClick={async () => {
            try {
              await api.battleStart(code);
              refresh();
            } catch (e) {
              alert(e.message);
            }
          }}
        >
          {participants.length < 2 ? "2人以上で開始できます" : "対戦を開始する"}
        </button>
      ) : (
        <p className="battle-room-hint">ホストの開始を待っています…</p>
      )}
    </div>
  );
}
