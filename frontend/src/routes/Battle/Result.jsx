import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import TierBadge from "../../components/TierBadge";

/** ランクの進捗バー。対戦後は「増減前 → 増減後」へアニメーションさせる。 */
function RankBar({ rank }) {
  const after = rank?.after;
  const before = rank?.before;
  const delta = rank?.delta ?? 0;
  // 最初は増減前の位置で描き、マウント直後に増減後へ動かす。
  const [width, setWidth] = useState(before?.progress ?? after?.progress ?? 0);

  useEffect(() => {
    if (!after) return undefined;
    const t = setTimeout(() => setWidth(after.progress), 500);
    return () => clearTimeout(t);
  }, [after]);

  if (!after?.tier) return null;

  return (
    <div className={`rank-bar-card${rank.promoted ? " promoted" : ""}`}>
      {rank.promoted && <p className="rank-promo">RANK UP!</p>}
      {rank.demoted && <p className="rank-demo">RANK DOWN</p>}

      <div className="rank-bar-head">
        <TierBadge tier={before?.tier ?? after.tier} large />
        <div className="rank-bar-track">
          <div className="rank-bar-fill" style={{ width: `${width}%` }} />
          <span className="rank-bar-pct">{width}%</span>
        </div>
        <TierBadge tier={after.next_tier ?? after.tier} large />
      </div>

      {delta !== 0 && (
        <p className={`rank-delta${delta > 0 ? " up" : " down"}`}>
          {delta > 0 ? "+" : ""}
          {delta} pt
        </p>
      )}
      <p className="rank-bar-note">
        現在 <b>{after.tier}</b> ランク
        {after.next_tier ? `（${after.next_tier}まであと ${100 - after.progress}%）` : "（最高ランク）"}
      </p>
    </div>
  );
}

export default function Result({ code }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.battleResult(code).then(setResult).catch((e) => setError(e.message));
  }, [code]);

  if (error) return <p className="error">{error}</p>;
  if (!result) return <p>読み込み中...</p>;

  const me = result.standings.find((r) => r.is_me);
  const opponent = result.standings.find((r) => !r.is_me);
  const won = me && opponent ? me.rank < opponent.rank : null;
  const draw = me && opponent && me.rank === opponent.rank;

  return (
    <div className="screen battle-result-screen">
      <div className={`result-banner${draw ? " draw" : won ? " win" : " lose"}`}>
        <span className="result-banner-text">
          {draw ? "DRAW" : won ? "WIN!" : "LOSE"}
        </span>
      </div>

      <div className="result-fighters">
        {[me, opponent].filter(Boolean).map((row, i) => (
          <div
            key={row.display_name + i}
            className={`result-fighter${row.is_me ? " me" : ""}${row.hp <= 0 ? " ko" : ""}`}
          >
            <div className="result-fighter-id">
              <span className="result-fighter-name">
                {row.display_name}
                {row.is_me && <span className="result-you">YOU</span>}
              </span>
              <span className="result-fighter-univ">{row.university ?? "所属未設定"}</span>
            </div>
            <div className="result-hp">
              <div className="result-hp-track">
                <div
                  className={`result-hp-fill${row.hp <= 30 ? " danger" : ""}`}
                  style={{ width: `${Math.max(0, row.hp)}%` }}
                />
              </div>
              <span className="result-hp-value">
                {Math.max(0, row.hp)}
                <span className="result-hp-unit">%</span>
              </span>
            </div>
            <span className="result-correct">正解 {row.correct_count}問</span>
            {row.left && <span className="result-left">途中退出</span>}
          </div>
        ))}
      </div>

      <RankBar rank={result.rank} />

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
