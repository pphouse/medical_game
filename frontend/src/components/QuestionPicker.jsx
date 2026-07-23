import { useEffect, useState } from "react";
import { api } from "../api";

const FILTERS = [
  { key: "all", label: "すべて" },
  { key: "unstudied", label: "未演習" },
  { key: "cross", label: "✕" },
  { key: "triangle", label: "△" },
  { key: "circle", label: "○" },
  { key: "double_circle", label: "◎" },
];

const EXAM_TYPE_LABEL = { CBT: "CBT", KOKUSHI: "医師国家試験" };

const MASTERY_LABEL = {
  double_circle: "◎",
  circle: "○",
  triangle: "△",
  cross: "✕",
  unstudied: "－",
};

function shuffle(array) {
  const result = [...array];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

export default function QuestionPicker({ category, onBack, onStart }) {
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

  const startSession = (orderedQuestions) =>
    onStart({ title: `分野別演習: ${category}`, questions: orderedQuestions });

  const startFromQuestion = (startIndex) => {
    const reordered = [...filtered.slice(startIndex), ...filtered.slice(0, startIndex)];
    startSession(reordered);
  };

  return (
    <div className="screen">
      <button className="back-link" onClick={onBack}>
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

      <div className="start-button-row">
        <button
          className="cta-button"
          disabled={filtered.length === 0}
          onClick={() => startSession(filtered)}
        >
          {filtered.length === 0 ? "対象の問題がありません" : "演習を始める"}
        </button>
        <button
          className="cta-button cta-button-secondary"
          disabled={filtered.length === 0}
          onClick={() => startSession(shuffle(filtered))}
        >
          シャッフルして始める
        </button>
      </div>

      {filtered.length > 0 && (
        <>
          <p className="question-list-count">
            {filtered.length}問中 1〜{filtered.length}問を表示
          </p>

          <div className="question-list">
            {filtered.map((q, i) => (
              <button
                key={q.id}
                className="question-row"
                onClick={() => startFromQuestion(i)}
              >
                <div className="question-row-badge">
                  <span className="question-row-examtype">{EXAM_TYPE_LABEL[q.exam_type] ?? q.exam_type}</span>
                  <span className="question-row-id">No.{q.id}</span>
                </div>
                <div className="question-row-body">
                  <p className="question-row-text">{q.question_text || "（本文なし）"}</p>
                  <div className="question-row-divider" />
                  <div className="question-row-meta">
                    <span className="question-row-topic">
                      {category}
                      {q.topic ? ` ＞ ${q.topic}` : ""}
                    </span>
                    <span>正答率：{q.correct_rate}%</span>
                    <span>結果：{MASTERY_LABEL[q.mastery_level] ?? "－"}</span>
                  </div>
                </div>
                <span className="question-row-arrow">›</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
