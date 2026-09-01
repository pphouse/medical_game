import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";

const CBT_BLOCK_COUNT = 6;

/** CBT模試（kind=cbt_once）は実際のCBTと同様に6ブロック構成で受験する。
 * ブロックの最後で「次」に進むと、そのブロックの問題には戻れなくなる
 * （実際のCBTのブロック制を簡易に再現。厳密な試験監督ではなく、
 * 学習ツールとして雰囲気を合わせる目的）。 */
function blockRangeFor(index, total) {
  const size = Math.max(1, Math.ceil(total / CBT_BLOCK_COUNT));
  const block = Math.floor(index / size);
  const start = block * size;
  const end = Math.min(start + size, total) - 1;
  return { block, size, start, end };
}

/** 模試の受験画面: 1問ずつ・フラグ・見直し一覧・サーバ基準タイマー。
 * 残り時間はサーバの deadline を真とし、フロントは表示のみ (spec フェーズ5)。 */
export default function Session() {
  const { examId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [flags, setFlags] = useState(() => new Set());
  const [showReview, setShowReview] = useState(false);
  const [remaining, setRemaining] = useState(null);
  const questionShownAt = useRef(performance.now());

  useEffect(() => {
    api
      .examQuestions(examId)
      .then((res) => {
        if (res.submitted_at) {
          navigate(`/exams/${examId}/result`, { replace: true });
          return;
        }
        setData(res);
        setAnswers(res.my_answers ?? {});
      })
      .catch((e) => setError(e.message));
  }, [examId, navigate]);

  useEffect(() => {
    if (!data?.deadline) return undefined;
    const tick = () => {
      const ms = new Date(data.deadline).getTime() - Date.now();
      setRemaining(Math.max(0, Math.floor(ms / 1000)));
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [data?.deadline]);

  useEffect(() => {
    questionShownAt.current = performance.now();
  }, [index]);

  const questions = data?.questions ?? [];
  const question = questions[index];
  const answeredCount = useMemo(
    () => questions.filter((q) => answers[q.id]).length,
    [questions, answers]
  );
  const isBlockExam = data?.kind === "cbt_once";
  const { block, start: blockStart, end: blockEnd } = blockRangeFor(index, questions.length);

  if (error) return <p className="error">{error}</p>;
  if (!data || !question) return <p>読み込み中...</p>;

  const timeUp = remaining === 0;

  async function select(key) {
    if (timeUp) return;
    setAnswers((prev) => ({ ...prev, [question.id]: key }));
    try {
      await api.examAnswer(examId, {
        question_id: question.id,
        selected_choice_key: key,
        response_time_ms: Math.round(performance.now() - questionShownAt.current),
      });
    } catch (e) {
      alert(e.message);
    }
  }

  async function handleSubmit() {
    const unanswered = questions.length - answeredCount;
    const message =
      unanswered > 0
        ? `未解答が${unanswered}問あります。提出しますか？（提出後は変更できません）`
        : "提出しますか？（提出後は変更できません）";
    if (!window.confirm(message)) return;
    try {
      await api.examSubmit(examId);
      navigate(`/exams/${examId}/result`, { replace: true });
    } catch (e) {
      alert(e.message);
    }
  }

  function toggleFlag() {
    setFlags((prev) => {
      const next = new Set(prev);
      if (next.has(question.id)) next.delete(question.id);
      else next.add(question.id);
      return next;
    });
  }

  const minutes = remaining != null ? Math.floor(remaining / 60) : null;
  const seconds = remaining != null ? remaining % 60 : null;

  if (showReview) {
    return (
      <div className="screen">
        <div className="quiz-topbar">
          <span className="quiz-topbar-title">
            {isBlockExam ? `見直し一覧（第${block + 1}ブロック）` : "見直し一覧"}
          </span>
          <span className="progress">
            解答 {answeredCount}/{questions.length}
          </span>
        </div>
        {isBlockExam && (
          <p className="exam-meta">
            CBT模試は他のブロックの問題を見直すことはできません（実際のCBTのブロック制と同じ）。
          </p>
        )}
        <div className="exam-grid">
          {questions.map((q, i) => {
            const outsideBlock = isBlockExam && (i < blockStart || i > blockEnd);
            return (
              <button
                key={q.id}
                className={`exam-grid-cell${answers[q.id] ? " answered" : ""}${
                  flags.has(q.id) ? " flagged" : ""
                }`}
                disabled={outsideBlock}
                onClick={() => {
                  setIndex(i);
                  setShowReview(false);
                }}
              >
                {i + 1}
                {flags.has(q.id) && "🚩"}
              </button>
            );
          })}
        </div>
        <button className="cta-button" onClick={handleSubmit}>
          提出する
        </button>
        <button className="toolbar-btn" onClick={() => setShowReview(false)}>
          問題に戻る
        </button>
      </div>
    );
  }

  return (
    <div className="screen">
      <div className="quiz-topbar">
        <span className="quiz-topbar-title">
          {isBlockExam && `第${block + 1}ブロック（全${CBT_BLOCK_COUNT}ブロック）　`}
          第{index + 1}問 / {questions.length}
        </span>
        <span className={`progress${timeUp || (remaining ?? 0) < 300 ? " exam-time-low" : ""}`}>
          残り {minutes != null ? `${minutes}:${String(seconds).padStart(2, "0")}` : "--:--"}
        </span>
      </div>

      {timeUp && (
        <div className="empty-card">
          制限時間が終了しました。解答は締め切られています。提出してください。
        </div>
      )}

      <div className="question-card">
        {question.case_stem && <p className="case-stem">{question.case_stem}</p>}
        <p className="question-text">{question.question_text}</p>
        <div className="choices">
          {question.choices.map((choice) => (
            <button
              key={choice.key}
              className={`choice${answers[question.id] === choice.key ? " selected" : ""}`}
              disabled={timeUp}
              onClick={() => select(choice.key)}
            >
              <span className="choice-key">{choice.key}</span>
              <span>{choice.text}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="bottom-toolbar">
        <button className="toolbar-btn" onClick={toggleFlag}>
          {flags.has(question.id) ? "🚩 解除" : "🚩 フラグ"}
        </button>
        <button
          className="toolbar-btn"
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0 || (isBlockExam && index === blockStart)}
        >
          ◁ 前
        </button>
        <button
          className="toolbar-btn"
          onClick={() => {
            if (isBlockExam && index === blockEnd && index < questions.length - 1) {
              if (
                !window.confirm(
                  `第${block + 1}ブロックを終了して、第${block + 2}ブロックに進みますか？` +
                    "このブロックの問題には、以後戻れません。"
                )
              ) {
                return;
              }
            }
            setIndex((i) => Math.min(questions.length - 1, i + 1));
          }}
          disabled={index === questions.length - 1}
        >
          次 ▷
        </button>
        <button className="toolbar-btn primary" onClick={() => setShowReview(true)}>
          見直し / 提出
        </button>
      </div>
    </div>
  );
}
