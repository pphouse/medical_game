import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
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

function formatResponseTime(ms) {
  if (ms == null) return null;
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}'${String(s).padStart(2, "0")}"`;
}

function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return `${String(d.getFullYear()).slice(2)}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function shuffled(arr) {
  const out = arr.slice();
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export default function QuestionPicker() {
  const { category } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // 同じ分野名が CBT と国試の両方にあるので、一覧で選んだ試験種別を持ち回る。
  const examType = searchParams.get("exam_type") ?? "";
  const soloUrl = `/solo${examType ? `?exam_type=${encodeURIComponent(examType)}` : ""}`;
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState(null);
  // 空集合 = 「すべて」（未選択時は全問表示）。個別のマステリー段階は複数選択できる。
  const [selected, setSelected] = useState(new Set());

  useEffect(() => {
    api
      .questions(category, examType ? { exam_type: examType } : {})
      .then(setQuestions)
      .catch((e) => setError(e.message));
  }, [category, examType]);

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
      <button className="back-link" onClick={() => navigate(soloUrl)}>
        ← 分野一覧に戻る
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

      <div className="start-button-row">
        <button
          className="cta-button"
          disabled={filtered.length === 0}
          onClick={() =>
            navigate("/quiz", {
              state: { title: `分野別演習: ${category}`, questions: filtered, backTo: soloUrl },
            })
          }
        >
          演習を始める ▶
        </button>
        <button
          className="cta-button cta-button-secondary"
          disabled={filtered.length === 0}
          onClick={() =>
            navigate("/quiz", {
              state: {
                title: `分野別演習: ${category}`,
                questions: shuffled(filtered),
                backTo: soloUrl,
              },
            })
          }
        >
          <span className="shuffle-icon">⇄</span> シャッフルして始める ▶
        </button>
      </div>

      <p className="course-count">
        {questions.length}問中 {filtered.length}問を表示
      </p>

      <div className="question-list">
        {filtered.map((q, i) => {
          const responseTime = formatResponseTime(q.last_response_time_ms);
          const answeredDate = formatDate(q.last_answered_at);
          return (
            <button
              key={q.id}
              className="question-row question-row-detailed"
              onClick={() =>
                navigate("/quiz", {
                  state: {
                    title: `分野別演習: ${category}`,
                    questions: filtered,
                    backTo: soloUrl,
                    startIndex: i,
                  },
                })
              }
            >
              <div className="question-row-main">
                <span className="question-row-no">{i + 1}</span>
                <span className="question-row-stem">
                  {q.case_stem || q.question_text || "（本文なし）"}
                </span>
              </div>
              <div className="question-row-meta">
                <span className="question-row-meta-line">
                  {q.category}
                  {q.topic && ` ＞ ${q.topic}`}
                </span>
                <span className="question-row-meta-line">
                  国試正答率：{q.correct_rate == null ? "集計中" : `${q.correct_rate}%`}
                  　結果：
                  {q.mastery_level !== "unstudied" && (
                    <span className={`question-row-mastery mastery-${q.mastery_level}`}>
                      {MASTERY_ICON[q.mastery_level]}
                    </span>
                  )}
                </span>
                <span className="question-row-meta-line">
                  解答時間：{responseTime ?? "－"}　演習日：{answeredDate ?? "－"}
                </span>
              </div>
              <span className="question-row-difficulty">{DIFFICULTY_LABEL[q.difficulty]}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
