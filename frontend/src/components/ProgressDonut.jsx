const LEVELS = ["double_circle", "circle", "triangle", "cross", "unstudied"];
const VAR_NAME = {
  double_circle: "--m-double",
  circle: "--m-circle",
  triangle: "--m-triangle",
  cross: "--m-cross",
  unstudied: "--m-unstudied",
};

/** 全体進捗を◎○△✕未演習の割合で色分けしたドーナツグラフで表示する。 */
export default function ProgressDonut({ counts, total, pct }) {
  const size = 58;
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;

  let offset = 0;
  const segments = LEVELS.map((level) => {
    const value = counts?.[level] ?? 0;
    const frac = total ? value / total : 0;
    const seg = { level, frac, offset };
    offset += frac;
    return seg;
  }).filter((s) => s.frac > 0);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="progress-donut">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="rgba(255,255,255,0.3)"
        strokeWidth={stroke}
      />
      {segments.map((s) => (
        <circle
          key={s.level}
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`var(${VAR_NAME[s.level]})`}
          strokeWidth={stroke}
          strokeDasharray={`${s.frac * c} ${c}`}
          strokeDashoffset={-s.offset * c}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      ))}
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" className="progress-donut-label">
        {pct}%
      </text>
    </svg>
  );
}
