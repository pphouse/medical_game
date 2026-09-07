import { useEffect, useState } from "react";
import { api } from "../api";

const METRIC_LABEL = { solved: "演習数", accuracy: "正答率" };

function niceMax(value) {
  if (value <= 0) return 10;
  const mag = 10 ** Math.floor(Math.log10(value));
  const step = mag / 2 || 1;
  return Math.ceil(value / step) * step;
}

/** 演習数×正答率の散布図。自分の点だけ濃い色で強調する。 */
function DistributionChart({ points }) {
  const w = 320;
  const h = 180;
  const pad = { l: 34, r: 12, t: 10, b: 24 };
  const maxSolved = niceMax(Math.max(1, ...points.map((p) => p.solved)));
  const x = (v) => pad.l + (v / maxSolved) * (w - pad.l - pad.r);
  const y = (v) => h - pad.b - (v / 100) * (h - pad.t - pad.b);

  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(maxSolved * f));
  const yTicks = [0, 25, 50, 75, 100];

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="scatter-chart">
      {yTicks.map((t) => (
        <line key={t} x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} className="scatter-grid" />
      ))}
      {yTicks.map((t) => (
        <text key={t} x={pad.l - 6} y={y(t)} className="scatter-axis-label" textAnchor="end" dominantBaseline="middle">
          {t}
        </text>
      ))}
      {xTicks.map((t) => (
        <text key={t} x={x(t)} y={h - pad.b + 14} className="scatter-axis-label" textAnchor="middle">
          {t}
        </text>
      ))}
      {points
        .filter((p) => !p.is_me)
        .map((p, i) => (
          <circle key={i} cx={x(p.solved)} cy={y(p.accuracy)} r={4} className="scatter-dot" />
        ))}
      {points
        .filter((p) => p.is_me)
        .map((p, i) => (
          <circle key={`me-${i}`} cx={x(p.solved)} cy={y(p.accuracy)} r={6} className="scatter-dot-me" />
        ))}
    </svg>
  );
}

// 演習数の縦軸は日ごとの実績に合わせて伸縮させず、300を基準に固定する
// （日によって目盛りが変わると増減が読み取れないため）。300を超える日が
// あるときだけ、その日が振り切れないよう100刻みで上に伸ばす。
const DAILY_AXIS_MAX = 300;
const DAILY_AXIS_STEP = 100;

function dailyAxisMax(counts) {
  const peak = Math.max(0, ...counts);
  if (peak <= DAILY_AXIS_MAX) return DAILY_AXIS_MAX;
  return Math.ceil(peak / DAILY_AXIS_STEP) * DAILY_AXIS_STEP;
}

/** 直近30日の演習数（自分のみ）。 */
function DailyChart({ daily }) {
  const w = 320;
  const h = 130;
  const pad = { l: 30, r: 8, t: 10, b: 20 };
  const max = dailyAxisMax(daily.map((d) => d.count));
  const stepX = (w - pad.l - pad.r) / Math.max(1, daily.length - 1);
  const x = (i) => pad.l + i * stepX;
  const y = (v) => h - pad.b - (v / max) * (h - pad.t - pad.b);
  // 100ごとの目盛り（0 は実線の基準線として別に引く）。
  const gridValues = [];
  for (let v = DAILY_AXIS_STEP; v <= max; v += DAILY_AXIS_STEP) gridValues.push(v);

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="scatter-chart">
      {gridValues.map((v) => (
        <line
          key={v}
          x1={pad.l}
          x2={w - pad.r}
          y1={y(v)}
          y2={y(v)}
          className="scatter-grid scatter-grid-dashed"
        />
      ))}
      {gridValues.map((v) => (
        <text
          key={`label-${v}`}
          x={pad.l - 6}
          y={y(v)}
          className="scatter-axis-label"
          textAnchor="end"
          dominantBaseline="middle"
        >
          {v}
        </text>
      ))}
      <line x1={pad.l} x2={w - pad.r} y1={y(0)} y2={y(0)} className="scatter-grid" />
      <text x={pad.l - 6} y={y(0)} className="scatter-axis-label" textAnchor="end" dominantBaseline="middle">
        0
      </text>
      {daily[0] && (
        <text x={x(0)} y={h - pad.b + 14} className="scatter-axis-label" textAnchor="start">
          {daily[0].date.slice(5)}
        </text>
      )}
      {daily[daily.length - 1] && (
        <text x={x(daily.length - 1)} y={h - pad.b + 14} className="scatter-axis-label" textAnchor="end">
          {daily[daily.length - 1].date.slice(5)}
        </text>
      )}
      {daily.map((d, i) => (
        <circle
          key={d.date}
          cx={x(i)}
          cy={y(d.count)}
          r={d.count > 0 ? 4 : 3}
          className={d.count > 0 ? "scatter-dot-me" : "scatter-dot-empty"}
        />
      ))}
    </svg>
  );
}

/** "YYYY-MM" を n ヶ月ずらす。 */
function shiftMonth(month, delta) {
  const [year, m] = month.split("-").map(Number);
  const zero = (year * 12 + (m - 1)) + delta;
  return `${Math.floor(zero / 12)}-${String((zero % 12) + 1).padStart(2, "0")}`;
}

function monthLabel(month) {
  const [year, m] = month.split("-").map(Number);
  return `${year}年${m}月`;
}

/** 演習状況（1ヶ月ぶん）。矢印で過去の月へ遡れる。 */
function DailySection({ range, daily, onChangeMonth }) {
  const month = range?.month;
  // 記録のある最初の月より前と、今月より先には進めない。
  const canGoBack = month && range.earliest_month && month > range.earliest_month;
  const canGoForward = month && range.latest_month && month < range.latest_month;

  return (
    <div className="mypage-card">
      <div className="daily-head">
        <button
          type="button"
          className="daily-nav"
          disabled={!canGoBack}
          aria-label="前の月"
          onClick={() => onChangeMonth(shiftMonth(month, -1))}
        >
          ◀
        </button>
        <h4 className="exam-section-heading daily-month">
          {month ? monthLabel(month) : ""}の演習状況
        </h4>
        <button
          type="button"
          className="daily-nav"
          disabled={!canGoForward}
          aria-label="次の月"
          onClick={() => onChangeMonth(shiftMonth(month, 1))}
        >
          ▶
        </button>
      </div>
      <p className="exam-meta daily-total">
        この月の演習数 {daily.reduce((sum, d) => sum + d.count, 0)}問
      </p>
      <DailyChart daily={daily} />
    </div>
  );
}

/** 順位の詳細（散布図・月ごとの演習状況・昨日の演習状況）。クリックして開く
 * モーダルではなく、ランキング画面の下に常時インラインで表示する。 */
export default function RankDetail({ scope, metric }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  // null は「今月」。矢印を押したらその月を覚える。
  const [month, setMonth] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    api
      .rankDetail(scope, metric, month)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [scope, metric, month]);

  return (
    <div className="rank-detail-inline">
      <h3 className="rank-detail-inline-title">{METRIC_LABEL[metric] ?? metric}の詳細</h3>

      {error && <p className="error">{error}</p>}
      {!data && !error && <p>読み込み中...</p>}

      {data && (
        <>
          <div className="mypage-card">
            <h4 className="exam-section-heading" style={{ marginTop: 0 }}>
              昨日（{data.yesterday.date}）の演習状況
            </h4>
            <div className="yesterday-stats">
              <div className="yesterday-stat">
                <span className="rank-tile-label">
                  {METRIC_LABEL[metric]}順位
                </span>
                <span className="rank-tile-value">
                  {data.me.eligible ? data.me.rank : "―"}
                  <span className="rank-tile-unit">位 / {data.me.out_of ?? 0}人中</span>
                </span>
              </div>
              <div className="yesterday-stat">
                <span className="rank-tile-label">演習数</span>
                <span className="rank-tile-value">
                  {data.yesterday.count}
                  <span className="rank-tile-unit">問</span>
                </span>
              </div>
              <div className="yesterday-stat">
                <span className="rank-tile-label">前日比</span>
                <span className="rank-tile-value">
                  {data.yesterday.diff > 0 ? "+" : data.yesterday.diff === 0 ? "±" : ""}
                  {data.yesterday.diff}
                </span>
              </div>
            </div>
          </div>

          <DailySection
            range={data.daily_range}
            daily={data.daily}
            onChangeMonth={setMonth}
          />

          <div className="mypage-card">
            <h4 className="exam-section-heading" style={{ marginTop: 0 }}>
              演習問題数に対する正答率分布
            </h4>
            {data.distribution.length === 0 ? (
              <p className="exam-meta">
                正答率ランキングは100問以上の解答が必要です。まだ分布を表示できる母集団がありません。
              </p>
            ) : (
              <>
                <DistributionChart points={data.distribution} />
                <p className="exam-meta">● あなたの位置　○ 他の学習者</p>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
