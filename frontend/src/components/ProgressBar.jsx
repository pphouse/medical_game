const MASTERY_LEVELS = ["double_circle", "circle", "triangle", "cross", "unstudied"];

export default function ProgressBar({ counts, total }) {
  if (!total) return <div className="progress-bar" />;
  return (
    <div className="progress-bar">
      {MASTERY_LEVELS.map((level) => {
        const pct = (counts[level] / total) * 100;
        if (pct <= 0) return null;
        return (
          <span
            key={level}
            className={`progress-seg seg-${level}`}
            style={{ width: `${pct}%` }}
          />
        );
      })}
    </div>
  );
}
