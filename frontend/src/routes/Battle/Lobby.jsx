import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";
import TierBadge from "../../components/TierBadge";

const POLL_INTERVAL_MS = 2000;

function QuickMatch({ onCancel }) {
  const navigate = useNavigate();
  const [ticket, setTicket] = useState(null);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function poll(ticketId) {
      try {
        const res = await api.battleQuickMatchPoll(ticketId);
        if (cancelled) return;
        setTicket(res);
        if (res.status === "matched" || res.status === "ai_matched") {
          timerRef.current = setTimeout(() => navigate(`/battle/${res.room_code}`), 2200);
        } else {
          timerRef.current = setTimeout(() => poll(ticketId), POLL_INTERVAL_MS);
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    }

    api
      .battleQuickMatch()
      .then((res) => {
        if (cancelled) return;
        setTicket(res);
        if (res.status === "matched" || res.status === "ai_matched") {
          timerRef.current = setTimeout(() => navigate(`/battle/${res.room_code}`), 2200);
        } else {
          timerRef.current = setTimeout(() => poll(res.ticket_id), POLL_INTERVAL_MS);
        }
      })
      .catch((e) => !cancelled && setError(e.message));

    return () => {
      cancelled = true;
      clearTimeout(timerRef.current);
    };
  }, [navigate]);

  if (error) return <p className="error">{error}</p>;

  const matched = ticket?.status === "matched" || ticket?.status === "ai_matched";

  return (
    <div className="mypage-card battle-card">
      {!matched ? (
        <>
          <h3 className="battle-card-title">対戦相手を探しています…</h3>
          <p className="exam-meta">
            同じランク帯を優先してマッチングします。1分見つからない場合はAI対戦になります。
            {ticket && `（経過 ${ticket.elapsed_seconds}秒）`}
          </p>
          <button className="toolbar-btn" style={{ width: "100%" }} onClick={onCancel}>
            キャンセル
          </button>
        </>
      ) : (
        <>
          <h3 className="battle-card-title">
            {ticket.status === "ai_matched" ? "AI対戦相手とマッチしました" : "マッチしました！"}
          </h3>
          <div className="battle-participant-row">
            <span>{ticket.me.display_name}（あなた）</span>
            <TierBadge tier={ticket.me.tier} />
          </div>
          <div className="battle-participant-row">
            <span>
              {ticket.opponent?.display_name}
              {ticket.opponent?.university ? ` ・ ${ticket.opponent.university}` : ""}
            </span>
            <TierBadge tier={ticket.opponent?.tier} />
          </div>
          <p className="exam-meta">まもなく対戦を開始します…</p>
        </>
      )}
    </div>
  );
}

export default function Lobby() {
  const navigate = useNavigate();
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [quickMatching, setQuickMatching] = useState(false);

  async function handleCreate() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.battleCreate();
      navigate(`/battle/${res.room_code}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleJoin(e) {
    e.preventDefault();
    if (!joinCode) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.battleJoin(joinCode.trim());
      navigate(`/battle/${res.room_code}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen">
      <h2>みんなで対戦クイズ</h2>
      {error && <p className="error">{error}</p>}

      {quickMatching ? (
        <QuickMatch onCancel={() => setQuickMatching(false)} />
      ) : (
        <div className="mypage-card battle-card">
          <h3 className="battle-card-title">クイックマッチ</h3>
          <p className="exam-meta">オンラインの中から同じランク帯の相手を優先してマッチングします。</p>
          <button className="cta-button" onClick={() => setQuickMatching(true)}>
            クイックマッチを開始
          </button>
        </div>
      )}

      <div className="mypage-card battle-card">
        <h3 className="battle-card-title">ルームをつくる</h3>
        <button className="cta-button" onClick={handleCreate} disabled={busy || quickMatching}>
          ルーム作成
        </button>
      </div>

      <div className="mypage-card battle-card">
        <h3 className="battle-card-title">ルームコードで参加</h3>
        <form onSubmit={handleJoin} className="battle-join-form">
          <input
            className="battle-code-input"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            placeholder="6桁コード"
            inputMode="numeric"
            maxLength={6}
            disabled={quickMatching}
          />
          <button
            className="cta-button"
            type="submit"
            disabled={busy || quickMatching || joinCode.length !== 6}
          >
            参加する
          </button>
        </form>
      </div>
    </div>
  );
}
