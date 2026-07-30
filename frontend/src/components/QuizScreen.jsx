import { useEffect, useState } from "react";
import { api } from "../api";
import { getCategoryTheme } from "../categoryTheme";

// ◎ and △ are only ever reached if the learner explicitly taps them; ○/✕
// are auto-assigned from correctness right after grading. 分からない is a
// distinct override that resets the question to unstudied (separate from a
// plain wrong answer, which auto-becomes ✕).
const OVERRIDE_OPTIONS = [
  { level: "double_circle", label: "◎", hint: "完璧" },
  { level: "triangle", label: "△", hint: "あいまい" },
  { level: "unstudied", label: "分からない", hint: "未演習に戻す" },
];

const MASTERY_DISPLAY = {
  double_circle: "◎",
  circle: "○",
  triangle: "△",
  cross: "✕",
  unstudied: "－",
};

const EXAM_TYPE_LABEL = { CBT: "CBT", KOKUSHI: "医師国家試験" };
const DIFFICULTY_LABEL = { 1: "易", 2: "標準", 3: "難" };

export default function QuizScreen({ title, questions, onBack, previewMode = false, startIndex = 0 }) {
  const [index, setIndex] = useState(startIndex);
  const [selectedKey, setSelectedKey] = useState(null);
  const [result, setResult] = useState(null); // grading response
  const [masteryLevel, setMasteryLevel] = useState(null); // current (auto or overridden)
  const [startedAt, setStartedAt] = useState(performance.now());
  const [score, setScore] = useState({ correct: 0, total: 0 });
  const [submitting, setSubmitting] = useState(false);

  const question = questions[index];
  // Category is intentionally not revealed anywhere before the question is
  // answered; it's only surfaced (via `theme`) in the result/explanation
  // panel once the learner has committed to an answer.
  const theme = question ? getCategoryTheme(question.category) : null;

  useEffect(() => {
    setSelectedKey(null);
    setResult(null);
    setMasteryLevel(null);
    setStartedAt(performance.now());
  }, [index]);

  if (!questions.length) {
    return (
      <div className="screen">
        <button className="back-link" onClick={onBack}>
          ← 戻る
        </button>
        <p>出題できる問題がありません。</p>
      </div>
    );
  }

  if (index >= questions.length) {
    const rate = score.total ? Math.round((score.correct / score.total) * 100) : 0;
    return (
      <div className="screen">
        <button className="back-link" onClick={onBack}>
          ← メニューに戻る
        </button>
        <div className="score-card">
          <h2>お疲れさまでした！</h2>
          <p className="score-summary">
            {score.total}問中 {score.correct}問正解（正答率 {rate}%）
          </p>
        </div>
      </div>
    );
  }

  async function handleSubmit() {
    if (!selectedKey || submitting) return;
    // previewMode (問題作成のプレビュー, phase 7): API を呼ばずローカル採点
    if (previewMode) {
      const correct = selectedKey === question.correct_choice_key;
      setResult({
        correct,
        correct_choice_key: question.correct_choice_key,
        explanation: question.explanation,
        mastery_level: correct ? "circle" : "cross",
      });
      setMasteryLevel(correct ? "circle" : "cross");
      setScore((s) => ({ correct: s.correct + (correct ? 1 : 0), total: s.total + 1 }));
      return;
    }
    setSubmitting(true);
    try {
      const responseTimeMs = Math.round(performance.now() - startedAt);
      const res = await api.submitAnswer({
        question_id: question.id,
        selected_choice_key: selectedKey,
        response_time_ms: responseTimeMs,
        context: title?.startsWith("復習") ? "review" : "solo",
      });
      setResult(res);
      setMasteryLevel(res.mastery_level);
      setScore((s) => ({
        correct: s.correct + (res.correct ? 1 : 0),
        total: s.total + 1,
      }));
    } catch (e) {
      alert(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOverride(level) {
    if (!result) return;
    setMasteryLevel(level);
    if (previewMode) return;
    try {
      await api.submitMastery(result.answer_history_id, level);
    } catch (e) {
      alert(e.message);
    }
  }

  function goPrev() {
    if (index > 0) setIndex((i) => i - 1);
  }

  function goNext() {
    if (result) setIndex((i) => i + 1);
  }

  return (
    <div className="screen">
      <button className="back-link" onClick={onBack}>
        ← メニューに戻る
      </button>

      <div className="quiz-topbar">
        <span className="quiz-topbar-title">{title}</span>
        <span className="progress">
          {index + 1} / {questions.length}
        </span>
      </div>

      <div className="question-card">
        <div className="badges">
          <span className="badge">{EXAM_TYPE_LABEL[question.exam_type]}</span>
          <span className="badge">難易度: {DIFFICULTY_LABEL[question.difficulty]}</span>
          <span className="badge">
            {question.correct_rate == null ? "正答率: 集計中" : `正答率: ${question.correct_rate}%`}
          </span>
          {question.question_type === "Q" && (
            <span className="badge">四連問 {question.set_order}/4</span>
          )}
        </div>
        {question.case_stem && <p className="case-stem">{question.case_stem}</p>}
        <p className="question-text">
          {question.question_text || "次の設問に最も適切なものを選んでください。"}
        </p>

        <div className="choices">
          {question.choices.map((choice) => {
            let cls = "choice";
            if (result) {
              if (choice.key === result.correct_choice_key) cls += " correct";
              else if (choice.key === selectedKey) cls += " incorrect";
            } else if (choice.key === selectedKey) {
              cls += " selected";
            }
            return (
              <button
                key={choice.key}
                className={cls}
                disabled={!!result || submitting}
                onClick={() => setSelectedKey(choice.key)}
              >
                <span className="choice-key">{choice.key}</span>
                <span>{choice.text}</span>
              </button>
            );
          })}
        </div>

        {!result && (
          <button
            className="cta-button"
            disabled={!selectedKey || submitting}
            onClick={handleSubmit}
          >
            {submitting ? "採点中..." : "解答する"}
          </button>
        )}

        {result && (
          <div className={`result-panel theme-${theme.key}`}>
            <div className="result-top-row">
              <p className={result.correct ? "verdict correct" : "verdict incorrect"}>
                {result.correct ? "○ 正解！" : "✕ 不正解"}
              </p>
              <span className="badge category-badge">分野: {question.category}</span>
            </div>
            <p className="explanation">{result.explanation}</p>
            <p className="mastery-prompt">
              現在の評価: <strong>{MASTERY_DISPLAY[masteryLevel]}</strong>
              　必要であれば下のボタンで上書きできます：
            </p>
            <div className="mastery-buttons">
              {OVERRIDE_OPTIONS.map((m) => (
                <button
                  key={m.level}
                  className={`mastery-button ${m.level}${masteryLevel === m.level ? " active" : ""}`}
                  onClick={() => handleOverride(m.level)}
                >
                  <span className="mastery-emoji">{m.label}</span>
                  <span className="mastery-hint">{m.hint}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="bottom-toolbar">
        <button className="toolbar-btn" onClick={onBack}>
          問題一覧
        </button>
        <button className="toolbar-btn" onClick={goPrev} disabled={index === 0}>
          ◁ 前の問題
        </button>
        <button className="toolbar-btn primary" onClick={goNext} disabled={!result}>
          次の問題 ▷
        </button>
      </div>
    </div>
  );
}
