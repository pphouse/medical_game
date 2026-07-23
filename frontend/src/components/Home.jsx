import { useEffect, useState } from "react";
import { api } from "../api";

const CATEGORY_ORDER = [
  "基礎医学", "公衆衛生", "臨床医学総論", "循環器", "呼吸器", "消化器", "腎臓",
  "内分泌代謝", "神経", "血液", "免疫", "感染症", "中毒・環境異常症", "救急",
  "小児", "産科", "婦人科", "泌尿器", "眼科", "耳鼻咽喉科", "皮膚", "精神",
  "整形", "麻酔", "放射線", "多選択肢", "四連問",
];

function sortByCategoryOrder(progress) {
  return [...progress].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)
  );
}

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
        {progress && sortByCategoryOrder(progress).map((p, i) => {
          const answered = p.total - p.remaining;
          return (
            <button
              key={p.category}
              className="course-row qb-row"
              onClick={() => onSelectCategory(p.category)}
            >
              <div className="qb-top">
                <span className="qb-bullet">{String.fromCharCode(65 + i)}</span>
                <span className="qb-name">{p.category}</span>
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
