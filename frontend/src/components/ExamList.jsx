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

const KIND_ORDER = ["large", "cbt_once", "monthly"];
const KIND_TITLE = {
  large: "国試模試（国試2ヶ月前に開催）",
  cbt_once: "CBT模試（生涯1回・4年生のみ）",
  monthly: "月次実力テスト（毎月1日）",
};
// どんな模試なのかの概要。開催中の回が無い学年でも「何があるか」は
// 分かるようにしたいので、模試の有無に関わらず常に出す。
const KIND_SUMMARY = {
  large: "本番の2ヶ月前に1回だけ開催する100問・180分の総合模試。分野別と総合の偏差値が出ます。対象は5年生以上。",
  cbt_once: "本番と同じ320問・6ブロック構成のCBT模試。生涯に1回だけ受験できます。対象は4年生。",
  monthly: "毎月1日に開催する15問・20分の実力テスト。CBT版と医師国家試験版があり、4年生以下は両方、5年生以上は国試版を受験できます。",
};
// その学年で受けられる回が無いときに、理由の見当がつくよう添える一言。
const KIND_EMPTY = {
  large: "いまは開催予定がありません。国試の2ヶ月前になると受験できます。",
  cbt_once: "対象は4年生です。学年はマイページから確認・変更できます。",
  monthly: "いまは開催中の回がありません。毎月1日に次の回が開きます。",
};

function groupByKind(exams) {
  const groups = {};
  for (const exam of exams) {
    (groups[exam.kind] ??= []).push(exam);
  }
  // 該当する回が無い種別も含めて全種別を並べる（何があるかの概要を出すため）。
  return KIND_ORDER.map((k) => ({
    kind: k,
    title: KIND_TITLE[k] ?? k,
    summary: KIND_SUMMARY[k],
    empty: KIND_EMPTY[k],
    exams: groups[k] ?? [],
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
      {groups.map((group) => (
        <div key={group.kind}>
          <h3 className="exam-section-heading">{group.title}</h3>
          <p className="exam-section-summary">{group.summary}</p>
          {group.exams.length === 0 && (
            <div className="empty-card exam-empty">{group.empty}</div>
          )}
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
                  {exam.target_grade_min != null &&
                    exam.target_grade_min === exam.target_grade_max &&
                    ` ・ 対象 ${exam.target_grade_min}年`}
                  {exam.target_grade_min != null &&
                    exam.target_grade_min !== exam.target_grade_max &&
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
