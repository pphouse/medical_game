import { useEffect, useState } from "react";
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

export default function ReviewDeck({ onStartSession }) {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.reviewDeck().then(setEntries).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!entries) return <p>読み込み中...</p>;

  if (entries.length === 0) {
    return (
      <div className="screen">
        <h2>復習問題</h2>
        <p>
          現在、復習対象の問題はありません。間違えた問題は自動でここに追加され、SM-2アルゴリズムに基づいたタイミングで再出題されます。
        </p>
      </div>
    );
  }

  const groups = groupByCategory(entries);
  const allQuestions = entries.map((e) => e.question);

  return (
    <div className="screen">
      <h2>復習問題</h2>
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
    </div>
  );
}
