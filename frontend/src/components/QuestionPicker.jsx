import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

const FILTERS = [
  { key: "all", label: "すべて" },
  { key: "unstudied", label: "未演習" },
  { key: "double_circle", label: "◎" },
  { key: "circle", label: "○" },
  { key: "triangle", label: "△" },
  { key: "cross", label: "✕" },
];

const MASTERY_ICON = {
  double_circle: "◎",
  circle: "○",
  triangle: "△",
  cross: "✕",
  unstudied: "－",
};

const DIFFICULTY_LABEL = { 1: "易", 2: "標準", 3: "難" };

export default function QuestionPicker() {
  const { category } = useParams();
  const navigate = useNavigate();
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState(null);
  // 空集合 = 「すべて」（未選択時は全問表示）。個別のマステリー段階は複数選択できる。
  const [selected, setSelected] = useState(new Set());

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
    selected.size === 0 ? questions : questions.filter((q) => selected.has(q.mastery_level));

  function toggleFilter(key) {
    if (key === "all") {
      setSelected(new Set());
      return;
    }
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="screen">
      <button className="back-link" onClick={() => navigate(-1)}>
        ← メニューに戻る
      </button>
      <h2>{category}：どの問題を解くか選ぶ</h2>

      <div className="filter-chip-row">
        {FILTERS.map((f) => {
          const active = f.key === "all" ? selected.size === 0 : selected.has(f.key);
          return (
            <button
              key={f.key}
              className={`filter-chip${active ? " active" : ""}`}
              onClick={() => toggleFilter(f.key)}
            >
              {f.label}
              <span className="filter-chip-count">{counts[f.key]}</span>
            </button>
          );
        })}
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

      <div className="question-list">
        {filtered.map((q, i) => (
          <button
            key={q.id}
            className="question-row"
            onClick={() =>
              navigate("/quiz", {
                state: {
                  title: `分野別演習: ${category}`,
                  questions: filtered,
                  backTo: "/",
                  startIndex: i,
                },
              })
            }
          >
            <span className="question-row-no">{i + 1}</span>
            <span className="question-row-stem">
              {q.case_stem || q.question_text || "（本文なし）"}
            </span>
            <span className={`question-row-mastery mastery-${q.mastery_level}`}>
              {MASTERY_ICON[q.mastery_level]}
            </span>
            <span className="question-row-difficulty">{DIFFICULTY_LABEL[q.difficulty]}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
