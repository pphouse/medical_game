import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";

const STATUS_LABEL = {
  scheduled: "開催予定",
  open: "受験可",
  closed: "採点待ち",
  graded: "採点済",
};

export default function List() {
  const navigate = useNavigate();
  const [exams, setExams] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.exams().then(setExams).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!exams) return <p>読み込み中...</p>;

  async function handleStart(exam) {
    try {
      if (!exam.my_result) await api.examStart(exam.id);
      navigate(`/exams/${exam.id}`);
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <div className="screen">
      <h2>模試</h2>
      {exams.length === 0 && (
        <div className="empty-card">開催予定の模試はまだありません。</div>
      )}
      {exams.map((exam) => {
        const started = Boolean(exam.my_result?.started_at);
        const submitted = Boolean(exam.my_result?.submitted_at);
        return (
          <div key={exam.id} className="mypage-card exam-card">
            <div className="exam-card-head">
              <span className="exam-title">{exam.title}</span>
              <span className={`exam-status exam-status-${exam.status}`}>
                {STATUS_LABEL[exam.status]}
              </span>
            </div>
            <p className="exam-meta">
              {new Date(exam.start_at).toLocaleString("ja-JP")} 開始 ・{" "}
              {exam.question_count}問 ・ {exam.duration_minutes}分
              {exam.target_grade_min &&
                ` ・ 対象 ${exam.target_grade_min}〜${exam.target_grade_max ?? 6}年`}
            </p>
            {exam.status === "open" && !submitted && (
              <button className="cta-button" onClick={() => handleStart(exam)}>
                {started ? "受験を再開する" : "受験を開始する"}
              </button>
            )}
            {exam.status === "graded" && started && (
              <button className="cta-button" onClick={() => navigate(`/exams/${exam.id}/result`)}>
                結果を見る
              </button>
            )}
            {submitted && exam.status !== "graded" && (
              <p className="exam-meta">提出済み。採点をお待ちください。</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
