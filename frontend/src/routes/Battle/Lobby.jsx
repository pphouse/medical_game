import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";

const QUESTION_COUNTS = [5, 10, 20];

export default function Lobby() {
  const navigate = useNavigate();
  const [questionCount, setQuestionCount] = useState(10);
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleCreate() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.battleCreate({ question_count: questionCount });
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
      <h2>みんなで早押しクイズ</h2>
      {error && <p className="error">{error}</p>}

      <div className="mypage-card battle-card">
        <h3 className="battle-card-title">ルームをつくる</h3>
        <div className="filter-chip-row">
          {QUESTION_COUNTS.map((n) => (
            <button
              key={n}
              className={`filter-chip${questionCount === n ? " active" : ""}`}
              onClick={() => setQuestionCount(n)}
            >
              {n}問
            </button>
          ))}
        </div>
        <button className="cta-button" onClick={handleCreate} disabled={busy}>
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
          />
          <button className="cta-button" type="submit" disabled={busy || joinCode.length !== 6}>
            参加する
          </button>
        </form>
      </div>
    </div>
  );
}
