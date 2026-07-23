import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useProfile } from "../context/ProfileContext";

function RankStat({ label, rankInfo }) {
  const display =
    rankInfo && rankInfo.rank ? `${rankInfo.rank}位 / ${rankInfo.out_of}人中` : "ランキング対象外";
  return (
    <div className="rank-stat">
      <span className="rank-label">{label}</span>
      <span className="rank-value">{display}</span>
    </div>
  );
}

const MODE_ICONS = {
  solo: (
    <svg viewBox="0 0 24 24" fill="none">
      <path
        d="M5 6.5A2.5 2.5 0 0 1 7.5 4H19v14.5H7.5A2.5 2.5 0 0 0 5 21V6.5Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M5 18.5A2.5 2.5 0 0 1 7.5 16H19" stroke="currentColor" strokeWidth="2" />
      <path d="M9.5 8.5h5M9.5 12h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  battle: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M13 3 5 13.5h5L10 21l8-11h-5L13 3Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  ),
  exams: (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="5" y="3.5" width="14" height="17" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M9 8h6M9 12h6M9 16h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  ranking: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M7 4h10v4a5 5 0 0 1-10 0V4Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path
        d="M7 5H4.5A1.5 1.5 0 0 0 3 6.5 4 4 0 0 0 7 10M17 5h2.5A1.5 1.5 0 0 1 21 6.5 4 4 0 0 1 17 10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path d="M12 13v4M9 20.5h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  review: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M4 12a8 8 0 1 1 2.6 5.9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17v-4h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 8.5V12l2.5 1.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  create: (
    <svg viewBox="0 0 24 24" fill="none">
      <path
        d="m14.5 5.5 4 4L8 20H4v-4L14.5 5.5Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="m12.5 7.5 4 4" stroke="currentColor" strokeWidth="2" />
    </svg>
  ),
};

const MODES = [
  { to: "/solo", icon: "solo", title: "ソロモード", desc: "分野別に自分のペースで演習" },
  { to: "/battle", icon: "battle", title: "みんなで早押しクイズ", desc: "友だちとリアルタイム対戦" },
  { to: "/exams", icon: "exams", title: "模試", desc: "全国順位・偏差値がわかる" },
  { to: "/ranking", icon: "ranking", title: "ランキング", desc: "学内・全国・大学別" },
  { to: "/review", icon: "review", title: "復習", desc: "忘却曲線に基づく復習デッキ" },
  {
    to: "/create",
    icon: "create",
    title: "問題をつくる",
    desc: "オリジナル問題を投稿",
    requiresVerification: true,
  },
];

export default function Menu() {
  const { profile } = useProfile();
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
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

      <div className="menu-grid">
        {MODES.map((mode) => {
          const locked = mode.requiresVerification && !profile?.student_verified;
          if (locked) {
            return (
              <div key={mode.to} className="menu-tile locked" aria-disabled="true">
                <span className="menu-tile-icon">{MODE_ICONS[mode.icon]}</span>
                <span className="menu-tile-title">{mode.title}</span>
                <span className="menu-tile-desc">学生証認証が必要です（マイページから申請）</span>
              </div>
            );
          }
          return (
            <Link key={mode.to} to={mode.to} className="menu-tile">
              <span className="menu-tile-icon">{MODE_ICONS[mode.icon]}</span>
              <span className="menu-tile-title">{mode.title}</span>
              <span className="menu-tile-desc">{mode.desc}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
