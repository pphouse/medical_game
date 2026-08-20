import { NavLink, Navigate, Outlet } from "react-router-dom";
import { useProfile } from "../../context/ProfileContext";

/** 管理画面の枠。moderator/admin 以外は入れない。
 *
 * サーバ側でも全エンドポイントを IsModerator / IsAdmin で守っている。
 * ここでの判定は画面を出さないためのもので、権限の実体はサーバ側にある。 */
export default function AdminLayout() {
  const { profile } = useProfile();

  if (!profile) return <p className="screen">読み込み中...</p>;
  if (profile.role !== "moderator" && profile.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  const tabs = [
    { to: "/admin", end: true, label: "ダッシュボード" },
    { to: "/admin/questions", label: "問題" },
    { to: "/admin/reports", label: "通報" },
    ...(profile.role === "admin" ? [{ to: "/admin/users", label: "ユーザー" }] : []),
  ];

  return (
    <div className="screen admin-screen">
      <div className="admin-header">
        <h2>管理画面</h2>
        <span className="badge">{profile.role === "admin" ? "管理者" : "モデレーター"}</span>
      </div>

      <div className="filter-chip-row">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) => `filter-chip${isActive ? " active" : ""}`}
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      <Outlet />
    </div>
  );
}
