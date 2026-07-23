import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useProfile } from "../context/ProfileContext";
import { supabase } from "../lib/supabase";

const ICONS = {
  rank: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M12 3 14.2 8.6 20 9.2 15.5 13 16.9 18.7 12 15.6 7.1 18.7 8.5 13 4 9.2 9.8 8.6 12 3Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  ),
  profile: (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8.2" r="3.2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M5 19.5c1.2-3.3 4-5 7-5s5.8 1.7 7 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  plan: (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="3.5" y="6" width="17" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3.5 10h17" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  ),
  trophy: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M7 4h10v4a5 5 0 0 1-10 0V4Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M7 5H4.5A1.5 1.5 0 0 0 3 6.5 4 4 0 0 0 7 10M17 5h2.5A1.5 1.5 0 0 1 21 6.5 4 4 0 0 1 17 10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M12 13v4M9 20.5h6M9.5 20.5 10 17M14.5 20.5 14 17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  university: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M4 10 12 5l8 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5.5 10.5v7M18.5 10.5v7M9 10.5v7M15 10.5v7" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 19.5h16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  grade: (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="4" y="5" width="16" height="15" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 9.5h16M8.5 3.5v3M15.5 3.5v3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  badge: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  ),
};

function SectionHeading({ icon, title }) {
  return (
    <h3 className="mypage-section-title">
      <span className="mypage-section-icon">{ICONS[icon]}</span>
      {title}
    </h3>
  );
}

export default function MyPage() {
  const { profile } = useProfile();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.summary().then(setSummary).catch(() => {});
  }, []);

  async function handleSignOut() {
    if (supabase) await supabase.auth.signOut();
    navigate("/auth", { replace: true });
  }

  if (!profile) {
    return (
      <div className="screen">
        <p>読み込み中...</p>
      </div>
    );
  }

  const user = profile;
  const fullName = user.display_name || "表示名未設定";
  const initial = (user.display_name || "?").charAt(0);

  return (
    <div className="screen">
      <div className="profile-hero">
        <span className="profile-avatar">{initial}</span>
        <div className="profile-hero-text">
          <span className="profile-hero-name">{fullName}</span>
          <span className="profile-hero-sub">
            {user.university?.name ?? "所属大学未設定"}
            {user.grade ? ` ・ ${user.grade}年` : ""}
          </span>
          {user.student_verified && (
            <span className="verified-badge">
              <span className="mypage-section-icon">{ICONS.badge}</span>
              学生証認証済み
            </span>
          )}
        </div>
      </div>

      <div className="mypage-section">
        <SectionHeading icon="rank" title="順位" />
        <div className="mypage-card">
          {summary ? (
            <div className="rank-tiles">
              <div className="rank-tile">
                <span className="rank-tile-value">
                  {summary.university_rank.rank ?? "―"}
                  <span className="rank-tile-unit">位</span>
                </span>
                <span className="rank-tile-label">学内順位 / {summary.university_rank.out_of}人中</span>
              </div>
              <div className="rank-tile">
                <span className="rank-tile-value">
                  {summary.national_rank.rank ?? "―"}
                  <span className="rank-tile-unit">位</span>
                </span>
                <span className="rank-tile-label">全国順位 / {summary.national_rank.out_of}人中</span>
              </div>
            </div>
          ) : (
            <p>読み込み中...</p>
          )}
        </div>
      </div>

      <div className="mypage-section">
        <SectionHeading icon="profile" title="プロフィール" />
        <div className="mypage-card">
          <div className="profile-row">
            <span className="profile-label">
              <span className="mypage-section-icon">{ICONS.profile}</span>
              表示名
            </span>
            <span className="profile-value">{fullName}</span>
          </div>
          <div className="profile-row">
            <span className="profile-label">
              <span className="mypage-section-icon">{ICONS.university}</span>
              所属大学
            </span>
            <span className="profile-value">{user.university?.name ?? "未設定"}</span>
          </div>
          <div className="profile-row">
            <span className="profile-label">
              <span className="mypage-section-icon">{ICONS.grade}</span>
              学年
            </span>
            <span className="profile-value">{user.grade ? `${user.grade}年` : "未設定"}</span>
          </div>
        </div>
      </div>

      <div className="mypage-section">
        <SectionHeading icon="plan" title="契約プラン" />
        <div className="mypage-card plan-card">
          <span className="plan-pill">無料プラン</span>
          <p>詳細は近日公開予定です。</p>
        </div>
      </div>

      <div className="mypage-section">
        <SectionHeading icon="trophy" title="実績" />
        <div className="mypage-card">
          <div className="achievement-grid">
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className="achievement-slot">
                {ICONS.trophy}
              </span>
            ))}
          </div>
          <p>詳細は近日公開予定です。</p>
        </div>
      </div>

      <div className="mypage-section">
        <button className="signout-button" onClick={handleSignOut}>
          ログアウト
        </button>
      </div>
    </div>
  );
}
