import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { useProfile } from "../../context/ProfileContext";

const STATUS_LABEL = {
  draft: "下書き",
  pending: "審査中",
  published: "公開中",
  rejected: "却下",
};

export default function MyQuestions() {
  const navigate = useNavigate();
  const { profile } = useProfile();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  const load = () => api.myQuestions().then(setRows).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  if (!profile?.student_verified) {
    return (
      <div className="screen">
        <h2>問題をつくる</h2>
        <div className="empty-card">
          問題の作成には学生証認証が必要です。
          <Link to="/settings/verification">こちらから申請</Link>してください。
        </div>
      </div>
    );
  }

  if (error) return <p className="error">{error}</p>;
  if (!rows) return <p>読み込み中...</p>;

  async function handleSubmit(id) {
    try {
      await api.submitQuestionForReview(id);
      load();
    } catch (e) {
      alert(e.message);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("この問題を削除しますか？")) return;
    try {
      await api.deleteQuestion(id);
      load();
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <div className="screen">
      <h2>自作問題の管理</h2>
      <button className="cta-button" onClick={() => navigate("/create/new")}>
        ＋ 新しい問題をつくる
      </button>
      {rows.length === 0 && (
        <div className="empty-card">
          まだ問題がありません。作成した問題は審査を経て公開されます。
        </div>
      )}
      {rows.map((q) => (
        <div key={q.id} className="mypage-card create-question-card">
          <div className="exam-card-head">
            <span className="exam-title">
              [{q.category}] {q.question_text.slice(0, 40)}
              {q.question_text.length > 40 && "…"}
            </span>
            <span className={`exam-status create-status-${q.status}`}>
              {STATUS_LABEL[q.status]}
            </span>
          </div>
          <p className="exam-meta">
            {q.visibility === "university_only" ? "学内限定" : "公開"} ・ 解答{" "}
            {q.answer_count}件 ・ {new Date(q.created_at).toLocaleDateString("ja-JP")}
          </p>
          <div className="create-actions">
            <button className="toolbar-btn" onClick={() => navigate(`/create/${q.id}/edit`)}>
              編集
            </button>
            {q.status === "draft" && (
              <button className="toolbar-btn primary" onClick={() => handleSubmit(q.id)}>
                審査に出す
              </button>
            )}
            <button className="toolbar-btn" onClick={() => handleDelete(q.id)}>
              削除
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
