import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";

const STATUS_LABEL = {
  draft: "下書き",
  pending: "審査待ち",
  published: "公開",
  rejected: "却下",
};
const EXAM_LABEL = { CBT: "CBT", KOKUSHI: "医師国家試験" };
const SOURCE_LABEL = { official: "公式", llm: "LLM生成", user: "ユーザー投稿" };

function Tiles({ title, data, labels }) {
  const entries = Object.entries(data ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="admin-block">
      <h3>{title}</h3>
      <div className="rank-tiles">
        {entries.map(([key, value]) => (
          <div key={key} className="rank-tile">
            <span className="rank-tile-label">{labels[key] ?? key}</span>
            <span className="rank-tile-value">{value}</span>
            <span className="rank-tile-unit">問</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.adminStats().then(setStats).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!stats) return <p>読み込み中...</p>;

  const pending = stats.by_status?.pending ?? 0;

  return (
    <>
      <div className="admin-block">
        <div className="rank-tiles">
          <div className="rank-tile">
            <span className="rank-tile-label">総問題数</span>
            <span className="rank-tile-value">{stats.total}</span>
            <span className="rank-tile-unit">問</span>
          </div>
          <div className="rank-tile">
            <span className="rank-tile-label">利用者</span>
            <span className="rank-tile-value">{stats.users}</span>
            <span className="rank-tile-unit">人</span>
          </div>
          <div className="rank-tile">
            <span className="rank-tile-label">通報</span>
            <span className="rank-tile-value">{stats.open_reports}</span>
            <span className="rank-tile-unit">件</span>
          </div>
        </div>
      </div>

      {pending > 0 && (
        <div className="admin-block">
          <Link className="cta-button" to="/admin/questions?status=pending">
            審査待ちの{pending}問を確認する
          </Link>
        </div>
      )}

      <Tiles title="状態別" data={stats.by_status} labels={STATUS_LABEL} />
      <Tiles title="試験種別" data={stats.by_exam_type} labels={EXAM_LABEL} />
      <Tiles title="出典別" data={stats.by_source} labels={SOURCE_LABEL} />

      <div className="admin-block">
        <h3>分野別（上位50）</h3>
        <table className="admin-table">
          <thead>
            <tr>
              <th>分野</th>
              <th>試験</th>
              <th className="num">問数</th>
            </tr>
          </thead>
          <tbody>
            {stats.categories.map((c) => (
              <tr key={`${c.exam_type}:${c.category}`}>
                <td>
                  <Link
                    to={`/admin/questions?category=${encodeURIComponent(c.category)}&exam_type=${c.exam_type}`}
                  >
                    {c.category}
                  </Link>
                </td>
                <td>{EXAM_LABEL[c.exam_type] ?? c.exam_type}</td>
                <td className="num">{c.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
