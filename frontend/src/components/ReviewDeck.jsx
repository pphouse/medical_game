import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

function groupByCategory(entries) {
  const groups = {};
  for (const e of entries) {
    const category = e.question.category;
    if (!groups[category]) groups[category] = [];
    groups[category].push(e.question);
  }
  return Object.entries(groups)
    .map(([category, questions]) => ({ category, questions }))
    .sort((a, b) => a.category.localeCompare(b.category, "ja"));
}

const TABS = [
  { key: "subject", label: "科目ごと" },
  { key: "exams", label: "模試" },
];

function SubjectReview({ onStartSession }) {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.reviewDeck().then(setEntries).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!entries) return <p>読み込み中...</p>;

  if (entries.length === 0) {
    return (
      <p>
        現在、復習対象の問題はありません。間違えた問題は自動でここに追加され、SM-2アルゴリズムに基づいたタイミングで再出題されます。
      </p>
    );
  }

  const groups = groupByCategory(entries);
  const allQuestions = entries.map((e) => e.question);

  return (
    <div className="course-list">
      <button
        key="all"
        className="course-row course-row-all"
        onClick={() => onStartSession({ title: "復習問題（すべて）", questions: allQuestions })}
      >
        <div className="course-row-top">
          <span className="course-letter">全</span>
          <span className="course-name">すべての科目</span>
          <span className="course-remaining">{allQuestions.length}問</span>
        </div>
      </button>

      {groups.map((g, i) => (
        <button
          key={g.category}
          className="course-row"
          onClick={() => onStartSession({ title: `復習問題: ${g.category}`, questions: g.questions })}
        >
          <div className="course-row-top">
            <span className="course-letter">{String.fromCharCode(65 + i)}</span>
            <span className="course-name">{g.category}</span>
            <span className="course-remaining">{g.questions.length}問</span>
          </div>
        </button>
      ))}
    </div>
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
      <h2>復習</h2>
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
