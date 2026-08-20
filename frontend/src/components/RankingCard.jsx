import { useEffect, useState } from "react";
import { api } from "../api";

const ICONS = {
  solved: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M5 19V10M12 19V5M19 19v-6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  ),
  accuracy: (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="m6 12 4 4 8-9" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

function topPercent(rank, total) {
  if (!rank || !total) return null;
  return Math.max(1, Math.round((rank / total) * 100));
}

function Tile({ icon, label, me }) {
  if (!me || me.eligible === false) {
    return (
      <div className="ranking-card-tile">
        <span className="ranking-card-tile-icon">{ICONS[icon]}</span>
        <div className="ranking-card-tile-body">
          <span className="ranking-card-tile-value">―</span>
          <span className="ranking-card-tile-label">{label}</span>
        </div>
      </div>
    );
  }
  const pct = topPercent(me.rank, me.total);
  return (
    <div className="ranking-card-tile">
      <span className="ranking-card-tile-icon">{ICONS[icon]}</span>
      <div className="ranking-card-tile-body">
        <span className="ranking-card-tile-value">
          {me.rank ?? "―"}
          <span className="ranking-card-tile-unit">位</span>
        </span>
        <span className="ranking-card-tile-label">{label}</span>
      </div>
      {pct != null && <span className="ranking-card-tile-pct">上位{pct}%</span>}
    </div>
  );
}

/** 問題演習のランキングカード：学内/全国を切り替えて演習数・正答率の順位を表示する。 */
export default function RankingCard() {
  const [scope, setScope] = useState("university");
  const [solved, setSolved] = useState(null);
  const [accuracy, setAccuracy] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setSolved(null);
    setAccuracy(null);
    api
      .ranking({ scope, metric: "solved", period: "all" })
      .then((d) => !cancelled && setSolved(d.me))
      .catch(() => {});
    api
      .ranking({ scope, metric: "accuracy", period: "all" })
      .then((d) => !cancelled && setAccuracy(d.me))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [scope]);

  return (
    <div className="ranking-card">
      <div className="ranking-card-toggle">
        <button
          className={scope === "university" ? "active" : ""}
          onClick={() => setScope("university")}
        >
          学内
        </button>
        <button
          className={scope === "national" ? "active" : ""}
          onClick={() => setScope("national")}
        >
          全国
        </button>
      </div>
      <Tile icon="solved" label="演習数" me={solved} />
      <Tile icon="accuracy" label="正答率" me={accuracy} />
    </div>
  );
}
