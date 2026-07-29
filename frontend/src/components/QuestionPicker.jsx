import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

const FILTERS = [
  { key: "all", label: "すべて" },
  { key: "unstudied", label: "未演習" },
  { key: "cross", label: "✕" },
  { key: "triangle", label: "△" },
  { key: "circle", label: "○" },
  { key: "double_circle", label: "◎" },
];

export default function QuestionPicker() {
  const { category } = useParams();
  const navigate = useNavigate();
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    api.questions(category).then(setQuestions).catch((e) => setError(e.message));
  }, [category]);

  if (error) return <p className="error">{error}</p>;
  if (!questions) return <p>読み込み中...</p>;

  const counts = { all: questions.length };
  for (const f of FILTERS) {
    if (f.key === "all") continue;
    counts[f.key] = questions.filter((q) => q.mastery_level === f.key).length;
  }

  const filtered =
    filter === "all" ? questions : questions.filter((q) => q.mastery_level === filter);

  return (
    <div className="screen">
      <button className="back-link" onClick={() => navigate(-1)}>
        ← メニューに戻る
      </button>
      <h2>{category}：どの問題を解くか選ぶ</h2>

      <div className="filter-chip-row">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`filter-chip${filter === f.key ? " active" : ""}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
            <span className="filter-chip-count">{counts[f.key]}</span>
          </button>
        ))}
      </div>

      <button
        className="cta-button"
        disabled={filtered.length === 0}
        onClick={() =>
          navigate("/quiz", {
            state: { title: `分野別演習: ${category}`, questions: filtered, backTo: "/" },
          })
        }
      >
        {filtered.length === 0 ? "対象の問題がありません" : `この内容で演習を始める（${filtered.length}問）`}
      </button>
    </div>
  );
}
