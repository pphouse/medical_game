import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";

const REASON_LABEL = {
  wrong_answer: "正解が誤っている",
  ambiguous: "設問が曖昧",
  typo: "誤字脱字",
  inappropriate: "不適切な内容",
  other: "その他",
};
const STATUS_LABEL = {
  draft: "下書き",
  pending: "審査待ち",
  published: "公開",
  rejected: "却下",
};

export default function AdminReports() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.adminReports().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>読み込み中...</p>;

  const rows = data.results ?? [];
  if (rows.length === 0) return <p className="empty-card">通報はありません。</p>;

  return (
    <div className="admin-block">
      {rows.map((r) => (
        <div key={r.id} className="admin-row">
          <div className="admin-row-body">
            <div className="admin-row-meta">
              <span className="badge admin-danger-badge">
                {REASON_LABEL[r.reason] ?? r.reason}
              </span>
              <span className={`badge create-status-${r.question_status}`}>
                {STATUS_LABEL[r.question_status] ?? r.question_status}
              </span>
              <span className="admin-note">
                {new Date(r.created_at).toLocaleString("ja-JP")}
              </span>
            </div>
            <Link to={`/admin/questions/${r.question_id}`} className="admin-row-text">
              {r.question_text?.slice(0, 90) || "(設問文なし)"}
            </Link>
            {r.detail && <p className="admin-note">{r.detail}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}
