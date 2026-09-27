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
  cbt_once: "CBT模試（7月1日〜3月31日・4年生のみ）",
  monthly: "月次実力テスト（毎月1日）",
};
// どんな模試なのかの概要。開催中の回が無い学年でも「何があるか」は
// 分かるようにしたいので、模試の有無に関わらず常に出す。
const KIND_SUMMARY = {
  large: "医師国家試験の2ヶ月前に1回だけ開催する100問・180分の総合模試。分野別と総合の偏差値が出ます。対象は5年生以上。",
  cbt_once: "本番と同じ320問・6ブロック構成のCBT模試。受験可能期間は7月1日から3月31日まで、期間中に1度だけ受験できます。出題は毎年4月1日に更新されます。対象は4年生。",
  monthly: "毎月1日に開催する15問・20分の実力テスト。4年生以下はCBT版、5年生以上は医師国家試験版を受験できます。",
};
// その学年で受けられる回が無いときに、理由の見当がつくよう添える一言。
const KIND_EMPTY = {
  large: "対象は5年生以上です。国試の2ヶ月前になると受験できます。",
  cbt_once: "対象は4年生です。受験可能期間は7月1日から3月31日までで、出題は毎年4月1日に更新されます。学年はマイページから確認・変更できます。",
  monthly: "今は開催中の回がありません。毎月1日に次の回が開きます。",
};

// 受験できるかどうかで3つに分ける。まず受けられるものを出し、そのあとに
// これから開くもの・終わったものを続ける。
const SECTIONS = [
  {
    key: "available",
    title: "受験できる模試",
    empty: "今受験できる模試はありません。",
    match: (e, submitted) => e.status === "open" && !submitted,
  },
  {
    key: "upcoming",
    title: "開催予定",
    empty: "開催予定の模試はありません。",
    match: (e) => e.status === "scheduled",
  },
  {
    key: "past",
    title: "開催済み",
    empty: "受験・開催が終わった模試はまだありません。",
    match: (e, submitted) => e.status !== "scheduled" && (submitted || e.status !== "open"),
  },
];

function groupByAvailability(exams) {
  // 種別（国試模試 → CBT模試 → 月次）の順は保ったまま、受験状況で振り分ける。
  const byKind = [...exams].sort(
    (a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind),
  );
  return SECTIONS.map((section) => ({
    ...section,
    exams: byKind.filter((e) =>
      section.match(e, Boolean(e.my_result?.submitted_at)),
    ),
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

  const sections = groupByAvailability(exams);

  return (
    <>
      {sections.map((section, i) => (
        <div
          key={section.key}
          // 受験できるものと、そうでないものを点線で区切る。
          className={`exam-section${i > 0 ? " exam-section-divided" : ""}`}
        >
          <h3 className="exam-section-heading">{section.title}</h3>
          {section.exams.length === 0 && (
            <div className="empty-card exam-empty">{section.empty}</div>
          )}
          {section.exams.map((exam) => {
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
                <p className="exam-card-kind">{KIND_TITLE[exam.kind] ?? exam.kind}</p>
                <p className="exam-meta">
                  {EXAM_TYPE_LABEL[exam.exam_type]} ・ {exam.question_count}問 ・{" "}
                  {exam.duration_minutes}分
                  {exam.kind === "cbt_once" && " ・ 7月1日〜3月31日に1度だけ"}
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
                  <>
                    {/* 得点・正誤・解説は提出直後から見られる。待つのは
                        順位や偏差値（成績）だけなので、そう書き分ける。 */}
                    <button
                      className="cta-button"
                      onClick={() => navigate(`/exams/${exam.id}/result`)}
                    >
                      採点結果を見る
                    </button>
                    <p className="exam-meta">
                      成績は翌月1日に確認できます。
                    </p>
                  </>
                )}
              </div>
            );
          })}
        </div>
      ))}

      {/* 受験状況で並べ替えたので、どんな模試があるかの概要はここにまとめる。
          その学年で受けられない種別も、理由が分かるように残す。 */}
      <div className="exam-section exam-section-divided">
        <h3 className="exam-section-heading">模試の種類</h3>
        {KIND_ORDER.map((kind) => (
          <div key={kind} className="exam-kind-note">
            <p className="exam-kind-note-title">{KIND_TITLE[kind]}</p>
            <p className="exam-section-summary">{KIND_SUMMARY[kind]}</p>
            {!exams.some((e) => e.kind === kind) && (
              <p className="exam-meta">{KIND_EMPTY[kind]}</p>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
