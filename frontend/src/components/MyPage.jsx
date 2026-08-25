import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useProfile } from "../context/ProfileContext";
import { STUDENT_VERIFICATION_ENABLED } from "../features";
import { supabase } from "../lib/supabase";
import TierBadge from "./TierBadge";

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
  exams: (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="3.5" y="6" width="17" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3.5 10h17" stroke="currentColor" strokeWidth="1.8" />
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

const EXAM_KIND_LABEL = { monthly: "月次模試", large: "大型模試" };

// "" は未選択で、学年から自動で決まる（サーバの resolved_exam_type が実効値）。
const EXAM_PREFERENCES = [
  { key: "", label: "学年に合わせる" },
  { key: "CBT", label: "CBT" },
  { key: "KOKUSHI", label: "医師国家試験" },
];

const EXAM_TYPE_LABEL = { CBT: "CBT", KOKUSHI: "医師国家試験" };

/** プロフィール編集フォーム。
 *
 * 所属大学は「未設定のときだけ」選べる。学内ランキングの母集団が所属大学で
 * 決まるため、あとから付け替えられると順位を操作できてしまう。サーバ側でも
 * 同じ制約を掛けてあるので、ここは UI 上の案内という位置づけ。 */
function ProfileEditor({ user, onCancel, onSaved }) {
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [grade, setGrade] = useState(user.grade ? String(user.grade) : "");
  const [universityId, setUniversityId] = useState(
    user.university?.id ? String(user.university.id) : ""
  );
  const [universities, setUniversities] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const universityLocked = Boolean(user.university);

  useEffect(() => {
    if (universityLocked) return;
    api.universities().then(setUniversities).catch(() => setUniversities([]));
  }, [universityLocked]);

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = { display_name: displayName.trim(), grade: grade ? Number(grade) : null };
      // 変更不可なので、確定済みの大学は送らない（サーバ側でも弾かれる）。
      if (!universityLocked && universityId) payload.university_id = Number(universityId);
      await api.updateMe(payload);
      await onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="profile-editor" onSubmit={handleSave}>
      <label className="profile-field">
        <span className="profile-field-label">表示名</span>
        <input
          type="text"
          value={displayName}
          maxLength={50}
          placeholder="表示名"
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </label>

      <label className="profile-field">
        <span className="profile-field-label">所属大学</span>
        {universityLocked ? (
          <>
            <input type="text" value={user.university.name} disabled />
            <span className="profile-field-hint">
              所属大学は学内ランキングの集計に使うため、あとから変更できません。
            </span>
          </>
        ) : (
          <>
            <select value={universityId} onChange={(e) => setUniversityId(e.target.value)}>
              <option value="">未設定</option>
              {(universities ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
            <span className="profile-field-hint">
              一度保存すると変更できません。よく確認して選んでください。
            </span>
          </>
        )}
      </label>

      <label className="profile-field">
        <span className="profile-field-label">学年</span>
        <div className="filter-chip-row">
          {["", 1, 2, 3, 4, 5, 6].map((g) => (
            <button
              key={g || "none"}
              type="button"
              className={`filter-chip${grade === String(g) ? " active" : ""}`}
              onClick={() => setGrade(String(g))}
            >
              {g === "" ? "未設定" : `${g}年`}
            </button>
          ))}
        </div>
      </label>

      {error && <p className="error">{error}</p>}

      <div className="profile-editor-actions">
        <button type="button" className="toolbar-btn" disabled={saving} onClick={onCancel}>
          キャンセル
        </button>
        <button type="submit" className="cta-button" disabled={saving}>
          {saving ? "保存中..." : "保存する"}
        </button>
      </div>
    </form>
  );
}

export default function MyPage() {
  const { profile, refresh } = useProfile();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [pointsInfo, setPointsInfo] = useState(null);
  const [examHistory, setExamHistory] = useState(null);
  const [editing, setEditing] = useState(false);
  const [savingPreference, setSavingPreference] = useState(false);
  const [preferenceError, setPreferenceError] = useState(null);

  useEffect(() => {
    api.summary().then(setSummary).catch(() => {});
    api.pointsRanking("national").then(setPointsInfo).catch(() => {});
    api.rankingExams().then(setExamHistory).catch(() => {});
  }, []);

  const seiseki = examHistory
    ? examHistory.filter(
        (r) => (r.kind === "monthly" || r.kind === "large") && r.submitted !== false
      )
    : null;

  async function handleExamPreference(value) {
    setSavingPreference(true);
    setPreferenceError(null);
    try {
      await api.updateMe({ exam_preference: value });
      await refresh();
    } catch (e) {
      setPreferenceError(e.message);
    } finally {
      setSavingPreference(false);
    }
  }

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
  const examPreference = user.exam_preference ?? "";

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
              <div className="rank-tile">
                <span className="rank-tile-value">
                  <TierBadge tier={pointsInfo?.me?.eligible ? pointsInfo.me.tier : null} large />
                </span>
                <span className="rank-tile-label">
                  対戦・模試ランク{pointsInfo?.me?.eligible ? `（${pointsInfo.me.points}pt）` : "（未ランク）"}
                </span>
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
          {editing ? (
            <ProfileEditor
              user={user}
              onCancel={() => setEditing(false)}
              onSaved={async () => {
                await refresh();
                setEditing(false);
              }}
            />
          ) : (
            <>
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
              <button className="toolbar-btn profile-edit-btn" onClick={() => setEditing(true)}>
                プロフィールを編集
              </button>
            </>
          )}
        </div>
      </div>

      <div className="mypage-section">
        <SectionHeading icon="exams" title="出題する試験" />
        <div className="mypage-card">
          <p className="exam-meta">
            演習と模試で既定にする試験です。「学年に合わせる」のままにしておくと、
            毎年4月1日の進級に合わせて自動で切り替わります（4年生以下はCBT、5年生以降は医師国家試験）。
          </p>
          <div className="filter-chip-row">
            {EXAM_PREFERENCES.map((p) => (
              <button
                key={p.key || "auto"}
                className={`filter-chip${examPreference === p.key ? " active" : ""}`}
                disabled={savingPreference}
                onClick={() => handleExamPreference(p.key)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <p className="exam-meta">
            現在の出題：<b>{EXAM_TYPE_LABEL[user.resolved_exam_type] ?? "―"}</b>
            {!examPreference && user.grade ? `（${user.grade}年生のため）` : ""}
          </p>
          {preferenceError && <p className="error">{preferenceError}</p>}
        </div>
      </div>

      <div className="mypage-section">
        <SectionHeading icon="exams" title="成績" />
        <div className="mypage-card">
          {seiseki === null ? (
            <p>読み込み中...</p>
          ) : seiseki.length === 0 ? (
            <p>まだ月次模試・大型模試の受験記録はありません。</p>
          ) : (
            seiseki.map((r) => (
              <div key={r.mock_exam_id} className="profile-row">
                <span className="profile-label">
                  {r.title}
                  <span className="profile-value" style={{ fontWeight: 400, marginLeft: 6 }}>
                    {EXAM_KIND_LABEL[r.kind]} ・ {new Date(r.start_at).toLocaleDateString("ja-JP")}
                  </span>
                </span>
                <button
                  className="profile-value"
                  style={{ background: "none", border: "none", color: "var(--accent)", fontWeight: 700 }}
                  onClick={() => navigate(`/exams/${r.mock_exam_id}/result`)}
                >
                  {r.score != null ? `${r.score}点 →` : "結果を見る →"}
                </button>
              </div>
            ))
          )}
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

      {(user.role === "moderator" || user.role === "admin") && (
        <div className="mypage-section">
          <button
            className="toolbar-btn"
            style={{ width: "100%" }}
            onClick={() => navigate("/admin")}
          >
            🛠 管理画面
          </button>
        </div>
      )}

      {STUDENT_VERIFICATION_ENABLED && !user.student_verified && (
        <div className="mypage-section">
          <button
            className="toolbar-btn"
            style={{ width: "100%" }}
            onClick={() => navigate("/settings/verification")}
          >
            🎓 学生証認証を申請
          </button>
        </div>
      )}

      <div className="mypage-section">
        <button className="signout-button" onClick={handleSignOut}>
          ログアウト
        </button>
      </div>
    </div>
  );
}
