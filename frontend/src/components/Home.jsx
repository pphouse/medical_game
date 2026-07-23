import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useProfile } from "../context/ProfileContext";
import ProgressBar from "./ProgressBar";

function RankStat({ label, rankInfo }) {
  const display = rankInfo && rankInfo.rank ? `${rankInfo.rank}位 / ${rankInfo.out_of}人中` : "ランキング対象外";
  return (
    <div className="rank-stat">
      <span className="rank-label">{label}</span>
      <span className="rank-value">{display}</span>
    </div>
  );
}

export default function Home() {
  const { profile } = useProfile();
  const navigate = useNavigate();
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
        {profile && (
          <p className="user-line">
            {profile.display_name || "名無し"} さん（{profile.university?.name ?? "所属大学未設定"}）
          </p>
        )}
      </div>

      {summary && (
        <div className="summary-card">
          <div className="summary-pct">
            <span className="summary-pct-value">{summary.overall_progress_pct}%</span>
            <span className="summary-pct-label">全体進捗（正答率 {summary.overall_correct_rate}%）</span>
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
        {progress?.map((p, i) => (
          <button
            key={p.category}
            className="course-row"
            onClick={() => navigate(`/solo/${encodeURIComponent(p.category)}`)}
          >
            <div className="course-row-top">
              <span className="course-letter">{String.fromCharCode(65 + i)}</span>
              <span className="course-name">
                {p.category} <span className="course-count">({p.total})</span>
              </span>
              <span className="course-remaining">残り{p.remaining}問</span>
            </div>
            <ProgressBar counts={p.counts} total={p.total} />
          </button>
        ))}
      </div>
    </div>
  );
}
