import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";

export default function Result({ code }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.battleResult(code).then(setResult).catch((e) => setError(e.message));
  }, [code]);

  if (error) return <p className="error">{error}</p>;
  if (!result) return <p>読み込み中...</p>;

  return (
    <div className="screen">
      <h2>対戦結果</h2>
      <div className="ranking-list">
        {result.standings.map((row) => (
          <div key={row.display_name} className={`ranking-row${row.is_me ? " me" : ""}`}>
            <span className={`ranking-rank${row.rank === 1 ? " top" : ""}`}>{row.rank}</span>
            <span className="ranking-name">
              {row.display_name}
              {row.is_me && "（あなた）"}
              <span className="ranking-univ">正解 {row.correct_count}問</span>
            </span>
            <span className="ranking-value">{row.score}点</span>
          </div>
        ))}
      </div>
      <div className="battle-result-actions">
        <Link to="/battle" className="cta-button battle-again-link">
          もう一度あそぶ
        </Link>
        <Link to="/" className="toolbar-btn battle-result-home">
          ホームに戻る
        </Link>
      </div>
    </div>
  );
}
