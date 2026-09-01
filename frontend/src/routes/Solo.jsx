import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { getCategoryTheme } from "../categoryTheme";
import ProgressBar from "../components/ProgressBar";
import ProgressDonut from "../components/ProgressDonut";
import { useProfile } from "../context/ProfileContext";
import { STUDENT_VERIFICATION_ENABLED } from "../features";

const MASTERY_LEGEND = [
  { level: "double_circle", label: "◎" },
  { level: "circle", label: "○" },
  { level: "triangle", label: "△" },
  { level: "cross", label: "✕" },
  { level: "unstudied", label: "－" },
];

/** 科目一覧の1行。タップで演習開始、シェブロンで内訳（評価の内訳バー）を
 * 開閉する。科目ごとの配色（categoryTheme）を帯びさせて、
 * 単色一覧よりも分野を目で拾いやすくしている。 */
function SubjectRow({ p, examType, navigate, expanded, onToggle }) {
  const theme = getCategoryTheme(p.category);
  const solved = p.total - p.remaining;

  const go = () =>
    navigate(
      `/solo/${encodeURIComponent(p.category)}${
        examType ? `?exam_type=${encodeURIComponent(examType)}` : ""
      }`,
    );

  return (
    <div className={`subject-row theme-${theme.key}`}>
      <div className="subject-row-top">
        <button className="subject-row-main" onClick={go}>
          <span className="subject-badge">{theme.letter}</span>
          <span className="subject-name">{p.category}</span>
          <span className="subject-total-pill">全{p.total}問</span>
          <span className="subject-arrow" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M5 12h13M13 6l6 6-6 6"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </button>
        <button
          className={`subject-toggle${expanded ? " open" : ""}`}
          onClick={onToggle}
          aria-label={expanded ? "内訳を閉じる" : "内訳を開く"}
          aria-expanded={expanded}
        >
          <svg viewBox="0 0 24 24" fill="none">
            <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      <p className="subject-stat">
        演習数：{solved}／{p.total}問
      </p>

      {expanded && (
        <div className="subject-detail">
          <ProgressBar counts={p.counts} total={p.total} />
          <div className="subject-legend">
            {MASTERY_LEGEND.map((m) => (
              <span key={m.level} className={`subject-legend-chip chip-${m.level}`}>
                {m.label} {p.counts[m.level]}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** 試験種別のタブ。CBT と国試は分野の切り方が違ううえ問題数も桁が近いので、
 * 混ぜて一覧にすると目的の分野を探せない。
 * 既定はマイページの設定（未選択なら学年から自動）。 */
const EXAM_TABS = [
  { key: "CBT", label: "CBT" },
  { key: "KOKUSHI", label: "医師国家試験" },
  { key: "", label: "すべて" },
];

const MASTERY_LEVELS = ["double_circle", "circle", "triangle", "cross", "unstudied"];

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

/** 問題演習: 全体進捗（円グラフ）・順位に続けて、分野別の演習リストを表示する
 * （旧「ホーム」と「ソロモード」を1画面に統合）。 */
export default function Solo() {
  const navigate = useNavigate();
  const { profile } = useProfile();
  const [searchParams, setSearchParams] = useSearchParams();
  // URL 指定が最優先。無ければマイページの設定（未選択なら学年から決まる
  // resolved_exam_type）に従う。プロフィール取得前は CBT を仮置きする。
  const examType = searchParams.get("exam_type") ?? profile?.resolved_exam_type ?? "CBT";
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [allCounts, setAllCounts] = useState(null); // 円グラフ用：学年フィルタなしの全体集計
  const [reviewDue, setReviewDue] = useState(0);
  const [expandedCategory, setExpandedCategory] = useState(null);

  useEffect(() => {
    api.summary().then(setSummary).catch(() => {});
    api
      .reviewSummary()
      .then((s) => setReviewDue(s.due_now))
      .catch(() => {});
    api
      .progress()
      .then((rows) => {
        const totals = Object.fromEntries(MASTERY_LEVELS.map((l) => [l, 0]));
        let total = 0;
        rows.forEach((row) => {
          total += row.total;
          MASTERY_LEVELS.forEach((l) => {
            totals[l] += row.counts[l] ?? 0;
          });
        });
        setAllCounts({ counts: totals, total });
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    setProgress(null);
    setError(null);
    api
      .progress(examType || undefined)
      .then((data) => {
        if (!cancelled) setProgress(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [examType]);

  const totalQuestions = progress?.reduce((sum, p) => sum + p.total, 0) ?? 0;

  return (
    <div className="screen">
      {summary && (
        <div className="summary-card">
          <ProgressDonut
            counts={allCounts?.counts}
            total={allCounts?.total}
            pct={summary.overall_progress_pct}
          />
          <div className="summary-pct">
            <span className="summary-pct-value">
              {summary.answered_count}/{summary.total_questions}問
            </span>
            <span className="summary-pct-label">
              全体進捗（正答率 {summary.overall_correct_rate}%）
            </span>
          </div>
          <div className="summary-ranks">
            <RankStat label="学内順位" rankInfo={summary.university_rank} />
            <RankStat label="全国順位" rankInfo={summary.national_rank} />
          </div>
        </div>
      )}

      <div className="quick-links">
        <button className="quick-link" onClick={() => navigate("/review")}>
          演習{reviewDue > 0 && <span className="menu-badge">{reviewDue > 99 ? "99+" : reviewDue}</span>}
        </button>
        {STUDENT_VERIFICATION_ENABLED && (
          <button className="quick-link" onClick={() => navigate("/create")}>
            問題をつくる
          </button>
        )}
      </div>

      <div className="filter-chip-row">
        {EXAM_TABS.map((tab) => (
          <button
            key={tab.key || "all"}
            className={`filter-chip${examType === tab.key ? " active" : ""}`}
            onClick={() =>
              setSearchParams(tab.key ? { exam_type: tab.key } : {}, { replace: true })
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {!progress && !error && <p>読み込み中...</p>}
      {progress?.length === 0 && <p>この試験種別の問題はまだありません。</p>}
      {progress?.length > 0 && (
        <p className="course-count">
          {progress.length}分野 / {totalQuestions}問
        </p>
      )}

      <div className="subject-list">
        {progress?.map((p) => (
          <SubjectRow
            key={p.category}
            p={p}
            examType={examType}
            navigate={navigate}
            expanded={expandedCategory === p.category}
            onToggle={() =>
              setExpandedCategory((c) => (c === p.category ? null : p.category))
            }
          />
        ))}
      </div>
    </div>
  );
}
