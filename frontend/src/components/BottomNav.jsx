import { NavLink } from "react-router-dom";

const ICONS = {
  home: (
    <svg viewBox="0 0 24 24" fill="none">
      <path
        d="M4 11.5 12 4l8 7.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M6 10v8.5a1 1 0 0 0 1 1h3.5v-5a1.5 1.5 0 0 1 1.5-1.5v0A1.5 1.5 0 0 1 13.5 14.5v5H17a1 1 0 0 0 1-1V10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  solo: (
    <svg viewBox="0 0 24 24" fill="none">
      <path
        d="M5 6.5A2.5 2.5 0 0 1 7.5 4H19v14.5H7.5A2.5 2.5 0 0 0 5 21V6.5Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M5 18.5A2.5 2.5 0 0 1 7.5 16H19" stroke="currentColor" strokeWidth="2" />
      <path d="M9.5 8.5h5M9.5 12h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  ranking: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M7 4h10v4a5 5 0 0 1-10 0V4Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path
        d="M7 5H4.5A1.5 1.5 0 0 0 3 6.5 4 4 0 0 0 7 10M17 5h2.5A1.5 1.5 0 0 1 21 6.5 4 4 0 0 1 17 10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path d="M12 13v4M9 20.5h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  battle: (
    <svg viewBox="0 0 24 24" fill="none">
      <path
        d="M13 3 5 13.5h5L10 21l8-11h-5L13 3Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  ),
  mypage: (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8.2" r="3.2" stroke="currentColor" strokeWidth="2" />
      <path
        d="M5 19.5c1.2-3.3 4-5 7-5s5.8 1.7 7 5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
};

const TABS = [
  { to: "/", icon: "home", label: "ホーム" },
  { to: "/solo", icon: "solo", label: "ソロ" },
  { to: "/battle", icon: "battle", label: "対戦" },
  { to: "/ranking", icon: "ranking", label: "ランキング" },
  { to: "/mypage", icon: "mypage", label: "マイページ" },
];

export default function BottomNav() {
  return (
    <nav className="bottom-nav">
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === "/"}
          className={({ isActive }) => `bottom-nav-item${isActive ? " active" : ""}`}
        >
          <span className="bottom-nav-icon">{ICONS[tab.icon]}</span>
          <span className="bottom-nav-label">{tab.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
