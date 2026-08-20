import { useEffect, useState } from "react";
import { api } from "../../api";
import { useProfile } from "../../context/ProfileContext";

const ROLES = [
  { value: "student", label: "学生" },
  { value: "moderator", label: "モデレーター" },
  { value: "admin", label: "管理者" },
];

export default function AdminUsers() {
  const { profile } = useProfile();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    api.adminUsers().then(setRows).catch((e) => setError(e.message));
  }, []);

  async function setRole(user, role) {
    setError(null);
    setNotice(null);
    try {
      await api.adminSetUserRole(user.id, role);
      setRows((prev) => prev.map((r) => (r.id === user.id ? { ...r, role } : r)));
      setNotice(`${user.display_name || "匿名ユーザー"} を「${
        ROLES.find((r) => r.value === role)?.label
      }」にしました。`);
    } catch (e) {
      setError(e.message);
    }
  }

  if (error && !rows) return <p className="error">{error}</p>;
  if (!rows) return <p>読み込み中...</p>;

  return (
    <>
      {error && <p className="error">{error}</p>}
      {notice && <p className="admin-notice">{notice}</p>}
      <div className="admin-block">
        <table className="admin-table">
          <thead>
            <tr>
              <th>表示名</th>
              <th>大学</th>
              <th>学年</th>
              <th>権限</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id}>
                <td>
                  {u.display_name || "匿名ユーザー"}
                  {u.id === profile?.id && <span className="badge">自分</span>}
                  {u.student_verified && <span className="verified-badge">認証済</span>}
                </td>
                <td>{u.university ?? "—"}</td>
                <td>{u.grade ?? "—"}</td>
                <td>
                  <select
                    value={u.role}
                    onChange={(e) => setRole(u, e.target.value)}
                    // 自分の管理者権限は外せない（最後の管理者が消えると誰も管理できない）
                    disabled={u.id === profile?.id}
                  >
                    {ROLES.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
