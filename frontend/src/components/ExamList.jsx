import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const STATUS_LABEL = {
  scheduled: "開催予定",
  open: "受験可",
  closed: "採点待ち",
  graded: "採点済",
};

const EXAM_TYPE_LABEL = { CBT: "CBT", KOKUSHI: "医師国家試験" };

const KIND_ORDER = ["large", "cbt_once", "monthly", "weekly"];
const KIND_TITLE = {
  large: "国試 大型模試（国試2ヶ月前に開催）",
  cbt_once: "CBT模試（生涯1回）",
  monthly: "月次模試（毎月1日）",
  weekly: "週次小テスト（毎週金曜）",
};

function groupByKind(exams) {
  const groups = {};
  for (const exam of exams) {
    (groups[exam.kind] ??= []).push(exam);
  }
  return KIND_ORDER.filter((k) => groups[k]?.length).map((k) => ({
    kind: k,
    title: KIND_TITLE[k] ?? k,
    exams: groups[k],
  }));
}

/** 現在受験できる／開催予定の模試の一覧。/exams（模試タブ）とランキングの
 * 「模試」カテゴリの両方から共通で使う。 */
export default function ExamList() {
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

  const groups = groupByKind(exams);

  return (
    <>
      {exams.length === 0 && (
        <div className="empty-card">
          現在あなたの学年で受験できる模試はありません。学年はマイページから確認・変更できます。
        </div>
      )}
      {groups.map((group) => (
        <div key={group.kind}>
          <h3 className="exam-section-heading">{group.title}</h3>
          {group.exams.map((exam) => {
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
                  {EXAM_TYPE_LABEL[exam.exam_type]} ・ {exam.question_count}問 ・{" "}
                  {exam.duration_minutes}分
                  {exam.kind === "cbt_once" && " ・ 生涯1回のみ"}
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
      ))}
    </>
  );
}
