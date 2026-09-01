import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useProfile } from "../context/ProfileContext";

const TABS = [
  { key: "subject", label: "科目ごと" },
  { key: "exams", label: "模試" },
];

// CBT と国試は分野の切り方が違ううえ問題数も桁が近いので、混ぜて一覧に
// すると目的の科目を探せない（問題演習画面と同じ理由・同じ既定値）。
const EXAM_TABS = [
  { key: "CBT", label: "CBT" },
  { key: "KOKUSHI", label: "医師国家試験" },
  { key: "", label: "すべて" },
];

const MASTERY_FILTERS = [
  { key: "unstudied", label: "未演習" },
  { key: "cross", label: "✕" },
  { key: "triangle", label: "△" },
  { key: "circle", label: "○" },
  { key: "double_circle", label: "◎" },
];

const ATTEMPT_FILTERS = [
  { key: "1", label: "1回" },
  { key: "2", label: "2回" },
  { key: "3plus", label: "3回以上" },
];

function toggle(set, key) {
  const next = new Set(set);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

/** 科目・評価・演習回数を掛け合わせて演習セットを作る。
 * 空集合は「絞り込まない」= 全部が対象。 */
function SubjectReview({ onStartSession }) {
  const { profile } = useProfile();
  // null は「まだ手動で選んでいない」＝マイページの設定（未選択なら学年から
  // 決まる resolved_exam_type）に従う。一度選んだらそれ以降はそちらを優先。
  const [examTypeOverride, setExamTypeOverride] = useState(null);
  const examType = examTypeOverride ?? profile?.resolved_exam_type ?? "CBT";
  const [categories, setCategories] = useState(null);
  const [selectedCategories, setSelectedCategories] = useState(new Set());
  const [selectedMastery, setSelectedMastery] = useState(new Set());
  const [selectedAttempts, setSelectedAttempts] = useState(new Set());
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setCategories(null);
    // 試験種別で分野の切り方が違うので、切り替えたら科目の絞り込みは
    // 一旦リセットする（前の試験種別にしかない科目が残ると混乱するため）。
    setSelectedCategories(new Set());
    api
      .progress(examType)
      .then((rows) => !cancelled && setCategories(rows.map((r) => r.category)))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [examType]);

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    api
      .reviewFilter({
        categories: [...selectedCategories],
        mastery: [...selectedMastery],
        attempts: [...selectedAttempts],
        examType,
      })
      .then((data) => !cancelled && setResult(data))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [selectedCategories, selectedMastery, selectedAttempts, examType]);

  if (error) return <p className="error">{error}</p>;
  if (!categories) return <p>読み込み中...</p>;

  const count = result?.count ?? 0;

  return (
    <>
      <div className="filter-group">
        <span className="filter-group-title">試験種別</span>
        <div className="filter-chip-row">
          {EXAM_TABS.map((t) => (
            <button
              key={t.key || "all"}
              className={`filter-chip${examType === t.key ? " active" : ""}`}
              onClick={() => setExamTypeOverride(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-group">
        <div className="filter-group-head">
          <span className="filter-group-title">科目</span>
          <div className="filter-group-actions">
            <button onClick={() => setSelectedCategories(new Set(categories))}>
              全科目チェック
            </button>
            <button onClick={() => setSelectedCategories(new Set())}>全科目クリア</button>
          </div>
        </div>
        <div className="filter-chip-row">
          {categories.map((c) => (
            <button
              key={c}
              className={`filter-chip${selectedCategories.has(c) ? " active" : ""}`}
              onClick={() => setSelectedCategories((s) => toggle(s, c))}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-group">
        <span className="filter-group-title">評価</span>
        <div className="filter-chip-row">
          {MASTERY_FILTERS.map((m) => (
            <button
              key={m.key}
              className={`filter-chip${selectedMastery.has(m.key) ? " active" : ""}`}
              onClick={() => setSelectedMastery((s) => toggle(s, m.key))}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-group">
        <span className="filter-group-title">演習回数</span>
        <div className="filter-chip-row">
          {ATTEMPT_FILTERS.map((a) => (
            <button
              key={a.key}
              className={`filter-chip${selectedAttempts.has(a.key) ? " active" : ""}`}
              onClick={() => setSelectedAttempts((s) => toggle(s, a.key))}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>

      <button
        className="cta-button"
        disabled={!result || count === 0}
        onClick={() =>
          onStartSession({
            title: "演習問題",
            questions: result.results,
            context: "review",
          })
        }
      >
        {!result
          ? "集計中..."
          : count === 0
            ? "条件に合う問題がありません"
            : `演習を始める（${count}問）`}
      </button>

      {result?.truncated && (
        <p className="course-count">
          該当が多いため、先頭{result.results.length}問を出題します。条件を絞ると狙った範囲だけ解けます。
        </p>
      )}
    </>
  );
}

const KIND_LABEL = {
  weekly: "週次小テスト",
  monthly: "月次模試",
  large: "大型模試",
  cbt_once: "CBT模試",
};

function ExamReview() {
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.rankingExams().then(setRows).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!rows) return <p>読み込み中...</p>;

  const submitted = rows.filter((r) => r.submitted !== false);
  if (submitted.length === 0) {
    return <p>まだ受験した模試がありません。「模試」タブから受験すると、ここで見直せます。</p>;
  }

  return (
    <div className="course-list">
      {submitted.map((r) => (
        <button
          key={r.mock_exam_id}
          className="course-row"
          onClick={() => navigate(`/exams/${r.mock_exam_id}/result`)}
        >
          <div className="course-row-top">
            <span className="course-name">
              {r.title}
              <span className="course-count"> {KIND_LABEL[r.kind] ?? ""}</span>
            </span>
            <span className="course-remaining">
              {new Date(r.start_at).toLocaleDateString("ja-JP")}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}

export default function ReviewDeck() {
  const navigate = useNavigate();
  const onStartSession = (session) =>
    navigate("/quiz", { state: { ...session, backTo: "/review" } });
  const [tab, setTab] = useState("subject");

  return (
    <div className="screen">
      <h2>演習</h2>
      <div className="filter-chip-row">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`filter-chip${tab === t.key ? " active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "subject" ? <SubjectReview onStartSession={onStartSession} /> : <ExamReview />}
    </div>
  );
}
