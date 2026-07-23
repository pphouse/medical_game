import { useEffect, useState } from "react";
import { api } from "../api";
import { sortByCategoryOrder } from "../categoryOrder";
import { shuffle } from "../shuffle";

function groupByCategory(entries) {
  const groups = {};
  for (const e of entries) {
    const category = e.question.category;
    if (!groups[category]) groups[category] = [];
    groups[category].push(e.question);
  }
  const grouped = Object.entries(groups).map(([category, questions]) => ({ category, questions }));
  return sortByCategoryOrder(grouped);
}

export default function ReviewDeck({ onStartSession }) {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);
  const [selectedCategories, setSelectedCategories] = useState(new Set());

  useEffect(() => {
    api
      .reviewDeck()
      .then((data) => {
        setEntries(data);
        setSelectedCategories(new Set(data.map((e) => e.question.category)));
      })
      .catch((e) => setError(e.message));
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

  function toggleCategory(category) {
    setSelectedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  const selectedQuestions = groups
    .filter((g) => selectedCategories.has(g.category))
    .flatMap((g) => g.questions);

  const startSelected = () => {
    const title =
      selectedCategories.size === groups.length
        ? "復習問題（すべて）"
        : selectedCategories.size === 1
        ? `復習問題: ${[...selectedCategories][0]}`
        : `復習問題（${selectedCategories.size}科目選択）`;
    onStartSession({ title, questions: shuffle(selectedQuestions) });
  };

  return (
    <div className="screen">
      <h2>復習問題</h2>

      <div className="review-select-box">
        <div className="review-select-header">
          <span>科目を選択（複数選択可）</span>
          <button
            className="review-select-all"
            onClick={() =>
              setSelectedCategories(
                selectedCategories.size === groups.length
                  ? new Set()
                  : new Set(groups.map((g) => g.category))
              )
            }
          >
            {selectedCategories.size === groups.length ? "すべて解除" : "すべて選択"}
          </button>
        </div>
        <div className="review-chip-row">
          {groups.map((g) => (
            <button
              key={g.category}
              className={`filter-chip${selectedCategories.has(g.category) ? " active" : ""}`}
              onClick={() => toggleCategory(g.category)}
            >
              {g.category}
              <span className="filter-chip-count">{g.questions.length}</span>
            </button>
          ))}
        </div>
        <button
          className="cta-button"
          disabled={selectedQuestions.length === 0}
          onClick={startSelected}
        >
          {selectedQuestions.length === 0
            ? "科目を選択してください"
            : `復習を始める（${selectedQuestions.length}問）`}
        </button>
      </div>

      <div className="course-list">
        <button
          key="all"
          className="course-row qb-row"
          onClick={() =>
            onStartSession({ title: "復習問題（すべて）", questions: shuffle(allQuestions) })
          }
        >
          <div className="qb-top">
            <span className="qb-bullet">全</span>
            <span className="qb-name">すべての科目</span>
            <span className="qb-count-badge">全{allQuestions.length}問</span>
            <span className="qb-arrow">→</span>
          </div>
        </button>

        {groups.map((g, i) => (
          <button
            key={g.category}
            className="course-row qb-row"
            onClick={() =>
              onStartSession({ title: `復習問題: ${g.category}`, questions: shuffle(g.questions) })
            }
          >
            <div className="qb-top">
              <span className="qb-bullet">{String.fromCharCode(65 + i)}</span>
              <span className="qb-name">{g.category}</span>
              <span className="qb-count-badge">全{g.questions.length}問</span>
              <span className="qb-arrow">→</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
