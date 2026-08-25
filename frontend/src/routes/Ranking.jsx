import { useEffect, useState } from "react";
import { api } from "../api";
import ExamList from "../components/ExamList";
import RankingCard from "../components/RankingCard";
import TierBadge from "../components/TierBadge";

const CATEGORIES = [
  { key: "practice", label: "問題演習" },
  { key: "battle", label: "対戦" },
  { key: "exams", label: "模試" },
];

const SCOPES = [
  { key: "national", label: "全国" },
  { key: "university", label: "学内" },
];

const PERIODS = [
  { key: "all", label: "通算" },
  { key: "month", label: "月間" },
];

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function formatValue(value) {
  if (value == null) return "―";
  return `${Math.round(value)}問`;
}

/** 画面上部の見出し。英字ロゴを重ねて、順位表の主役感を出す。 */
function RankingHeading() {
  return (
    <div className="ranking-heading">
      <h2 className="ranking-heading-ja">ランキング</h2>
      <span className="ranking-heading-en" aria-hidden="true">
        RANKING
      </span>
    </div>
  );
}

function ChipRow({ options, value, onChange }) {
  return (
    <div className="filter-chip-row">
      {options.map((o) => (
        <button
          key={o.key}
          className={`filter-chip${value === o.key ? " active" : ""}`}
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function RankingTable({ data }) {
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
          </span>
          <span className="ranking-value">{formatValue(entry.value)}</span>
        </div>
      ))}
    </div>
  );
}

/** 問題演習の順位表。全国/学内 × 通算/月間 で切り替える。 */
function PracticeRanking({ scope, period }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .ranking({ scope, metric: "solved", period: period === "month" ? currentMonth() : "all" })
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [scope, period]);

  return (
    <>
      <RankingCard scope={scope} />
      {error && <p className="error">{error}</p>}
      {data?.me && (
        <div className="ranking-me-card">
          {data.me.eligible === false ? (
            <span className="ranking-me-reason">{data.me.reason}</span>
          ) : (
            <>
              <span className="ranking-me-label">あなたの順位</span>
              <span className="ranking-me-rank">{data.me.rank ? `${data.me.rank}位` : "―"}</span>
              <span className="ranking-me-value">{formatValue(data.me.value)}</span>
            </>
          )}
        </div>
      )}
      <RankingTable data={data} />
    </>
  );
}

/** 対戦・模試の合算ポイント順位。ポイントは累計値なので期間の絞り込みは無い。 */
function PointsRanking({ scope }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .pointsRanking(scope)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [scope]);

  return (
    <>
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
            <div
              key={`${entry.rank}-${entry.display_name}`}
              className={`ranking-row${entry.is_me ? " me" : ""}`}
            >
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

/** 模試カテゴリ: 受験できる模試の一覧と、自分の受験履歴（順位・点数）。
 * 全国/学内の切り替えは持たない（履歴は自分のものだけなので）。 */
function ExamsTab() {
  return (
    <>
      <ExamList />
      <h3 className="exam-section-heading">これまでの成績</h3>
      <ExamHistory />
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
  const [period, setPeriod] = useState("all");

  return (
    <div className="screen">
      <RankingHeading />

      <ChipRow options={CATEGORIES} value={category} onChange={setCategory} />

      {/* 模試は自分の受験履歴なので、全国/学内の絞り込みは出さない。 */}
      {category !== "exams" && <ChipRow options={SCOPES} value={scope} onChange={setScope} />}

      {/* 対戦のポイントは累計値のため、通算/月間は問題演習にだけ出す。 */}
      {category === "practice" && (
        <ChipRow options={PERIODS} value={period} onChange={setPeriod} />
      )}

      {category === "practice" && <PracticeRanking scope={scope} period={period} />}
      {category === "battle" && <PointsRanking scope={scope} />}
      {category === "exams" && <ExamsTab />}
    </div>
  );
}
