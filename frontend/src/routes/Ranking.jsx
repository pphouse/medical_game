import { useEffect, useState } from "react";
import { api } from "../api";
import RankingCard from "../components/RankingCard";
import TierBadge from "../components/TierBadge";

const CATEGORIES = [
  { key: "practice", label: "問題演習" },
  { key: "battle", label: "対戦" },
];

const SCOPES = [
  { key: "national", label: "全国" },
  { key: "university", label: "学内" },
  { key: "university_aggregate", label: "大学別" },
  { key: "exams", label: "模試履歴" },
];

const METRICS = [
  { key: "solved", label: "問題数" },
  { key: "accuracy", label: "正答率" },
];

const PERIODS = [
  { key: "all", label: "通算" },
  { key: "month", label: "月間" },
];

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function formatValue(metric, value) {
  if (value == null) return "―";
  return metric === "accuracy" ? `${value}%` : `${Math.round(value)}問`;
}

function RankingTable({ data, metric }) {
  if (!data) return <p>読み込み中...</p>;
  if (data.entries.length === 0) {
    return <div className="empty-card">まだ集計データがありません。</div>;
  }
  return (
    <div className="ranking-list">
      {data.entries.map((entry, i) => (
        <div
          key={`${entry.rank}-${entry.display_name ?? entry.university}-${i}`}
          className={`ranking-row${entry.is_me ? " me" : ""}`}
        >
          <span className={`ranking-rank${entry.rank <= 3 ? " top" : ""}`}>{entry.rank}</span>
          <span className="ranking-name">
            {entry.display_name ?? entry.university ?? "匿名ユーザー"}
            {entry.display_name && entry.university && (
              <span className="ranking-univ">{entry.university}</span>
            )}
            {entry.sample_size != null && (
              <span className="ranking-univ">対象 {entry.sample_size}人</span>
            )}
          </span>
          <span className="ranking-value">{formatValue(metric, entry.value)}</span>
        </div>
      ))}
    </div>
  );
}

function PointsRanking() {
  const [scope, setScope] = useState("national");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api.pointsRanking(scope).then(setData).catch((e) => setError(e.message));
  }, [scope]);

  return (
    <>
      <div className="filter-chip-row">
        <button
          className={`filter-chip${scope === "national" ? " active" : ""}`}
          onClick={() => setScope("national")}
        >
          全国
        </button>
        <button
          className={`filter-chip${scope === "university" ? " active" : ""}`}
          onClick={() => setScope("university")}
        >
          学内
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {data?.me && (
        <div className="ranking-me-card">
          {data.me.eligible === false ? (
            <span className="ranking-me-reason">{data.me.reason}</span>
          ) : (
            <>
              <span className="ranking-me-label">あなたのランク</span>
              <span className="ranking-me-rank">
                <TierBadge tier={data.me.tier} large />
              </span>
              <span className="ranking-me-value">{data.me.points}pt</span>
            </>
          )}
        </div>
      )}

      {!data ? (
        <p>読み込み中...</p>
      ) : data.entries.length === 0 ? (
        <div className="empty-card">まだ対戦・模試でポイントを獲得したユーザーがいません。</div>
      ) : (
        <div className="ranking-list">
          {data.entries.map((entry) => (
            <div key={`${entry.rank}-${entry.display_name}`} className={`ranking-row${entry.is_me ? " me" : ""}`}>
              <span className={`ranking-rank${entry.rank <= 3 ? " top" : ""}`}>{entry.rank}</span>
              <span className="ranking-name">
                {entry.display_name}
                {entry.university && <span className="ranking-univ">{entry.university}</span>}
              </span>
              <TierBadge tier={entry.tier} fallback="―" />
              <span className="ranking-value">{entry.points}pt</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function ExamHistory() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api.rankingExams().then(setRows).catch((e) => setError(e.message));
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!rows) return <p>読み込み中...</p>;
  if (rows.length === 0) {
    return <div className="empty-card">受験した模試はまだありません。</div>;
  }
  return (
    <div className="ranking-list">
      {rows.map((r) => (
        <div key={r.mock_exam_id} className="ranking-row">
          <span className="ranking-name">
            {r.title}
            <span className="ranking-univ">
              {new Date(r.start_at).toLocaleDateString("ja-JP")}
            </span>
          </span>
          <span className="ranking-value">
            {r.rank ? `${r.rank}位` : "採点中"}（{r.score}点）
          </span>
        </div>
      ))}
    </div>
  );
}

export default function Ranking() {
  const [category, setCategory] = useState("practice");
  const [scope, setScope] = useState("national");
  const [metric, setMetric] = useState("solved");
  const [period, setPeriod] = useState("all");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (category !== "practice" || scope === "exams") return;
    setData(null);
    setError(null);
    api
      .ranking({ scope, metric, period: period === "month" ? currentMonth() : "all" })
      .then(setData)
      .catch((e) => setError(e.message));
  }, [category, scope, metric, period]);

  return (
    <div className="screen">
      <h2>ランキング</h2>

      <div className="filter-chip-row">
        {CATEGORIES.map((c) => (
          <button
            key={c.key}
            className={`filter-chip${category === c.key ? " active" : ""}`}
            onClick={() => setCategory(c.key)}
          >
            {c.label}
          </button>
        ))}
      </div>

      {category === "battle" ? (
        <PointsRanking />
      ) : (
        <>
          <RankingCard />

          <div className="filter-chip-row">
            {SCOPES.map((s) => (
              <button
                key={s.key}
                className={`filter-chip${scope === s.key ? " active" : ""}`}
                onClick={() => setScope(s.key)}
              >
                {s.label}
              </button>
            ))}
          </div>

          {scope === "exams" ? (
            <ExamHistory />
          ) : (
            <>
              <div className="filter-chip-row">
                {METRICS.map((m) => (
                  <button
                    key={m.key}
                    className={`filter-chip${metric === m.key ? " active" : ""}`}
                    onClick={() => setMetric(m.key)}
                  >
                    {m.label}
                  </button>
                ))}
                <span className="ranking-separator" />
                {PERIODS.map((p) => (
                  <button
                    key={p.key}
                    className={`filter-chip${period === p.key ? " active" : ""}`}
                    onClick={() => setPeriod(p.key)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              {error && <p className="error">{error}</p>}

              {data?.me && (
                <div className="ranking-me-card">
                  {data.me.eligible === false ? (
                    <span className="ranking-me-reason">{data.me.reason}</span>
                  ) : (
                    <>
                      <span className="ranking-me-label">あなたの順位</span>
                      <span className="ranking-me-rank">
                        {data.me.rank ? `${data.me.rank}位` : "―"}
                      </span>
                      <span className="ranking-me-value">{formatValue(metric, data.me.value)}</span>
                    </>
                  )}
                </div>
              )}

              <RankingTable data={data} metric={metric} />
            </>
          )}
        </>
      )}
    </div>
  );
}
