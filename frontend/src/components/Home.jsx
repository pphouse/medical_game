import { useEffect, useState } from "react";
import { api } from "../api";
import { sortByCategoryOrder } from "../categoryOrder";

const MASTERY_LEVELS = ["double_circle", "circle", "triangle", "cross", "unstudied"];

function RankStat({ label, rankInfo }) {
  const display = rankInfo && rankInfo.rank ? `${rankInfo.rank}位 / ${rankInfo.out_of}人中` : "ランキング対象外";
  return (
    <div className="rank-stat">
      <span className="rank-label">{label}</span>
      <span className="rank-value">{display}</span>
    </div>
  );
}

export default function Home({ user, onSelectCategory }) {
  const [progress, setProgress] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.progress().then(setProgress).catch((e) => setError(e.message));
    api.summary().then(setSummary).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="screen home">
      <div className="home-header">
        <h1>
          <span className="title-main">CBT・国試対策クイズ</span>
          <span className="title-sub">AIが弱点を見抜く、あなただけの合格戦略。</span>
        </h1>
        {user && (
          <p className="user-line">
            {user.username} さん（{user.university?.name ?? "所属大学未設定"}）
          </p>
        )}
      </div>

      {summary && (
        <div className="summary-card">
          <div className="summary-pct">
            <span className="summary-ring" style={{ "--pct": summary.overall_progress_pct }}>
              <span className="summary-ring-value">{summary.overall_progress_pct}%</span>
            </span>
            <div className="summary-pct-col">
              <span className="summary-pct-value">
                {summary.answered_count}/{summary.total_count}問
              </span>
              <span className="summary-pct-label">全体進捗（正答率 {summary.overall_correct_rate}%）</span>
            </div>
          </div>
          <div className="summary-ranks">
            <RankStat label="学内順位" rankInfo={summary.university_rank} />
            <RankStat label="全国順位" rankInfo={summary.national_rank} />
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {!progress && !error && <p>読み込み中...</p>}

      <div className="course-list">
        {progress && sortByCategoryOrder(progress).map((p, i) => {
          const answered = p.total - p.remaining;
          const progressPct = p.total > 0 ? Math.round((answered / p.total) * 100) : 0;
          return (
            <button
              key={p.category}
              className="course-row qb-row"
              onClick={() => onSelectCategory(p.category)}
            >
              <div className="qb-top">
                <span className="qb-bullet">{String.fromCharCode(65 + i)}</span>
                <span className="qb-name">{p.category}</span>
                <span className="qb-progress-wrap">
                  <span className="qb-progress-bar">
                    {MASTERY_LEVELS.map(
                      (level) =>
                        p.counts[level] > 0 && (
                          <span
                            key={level}
                            className={`progress-seg seg-${level}`}
                            style={{ width: `${(p.counts[level] / p.total) * 100}%` }}
                          />
                        )
                    )}
                  </span>
                  <span className="qb-progress-pct">{progressPct}%</span>
                </span>
                <span className="qb-count-badge">全{p.total}問</span>
                <span className="qb-arrow">→</span>
              </div>
              <div className="qb-divider" />
              <div className="qb-stats">
                演習数：{answered}　正解率：{p.correct_rate}%
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
