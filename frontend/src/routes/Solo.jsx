import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import ProgressBar from "../components/ProgressBar";

/** 試験種別のタブ。CBT と国試は分野の切り方が違ううえ問題数も桁が近いので、
 * 混ぜて一覧にすると目的の分野を探せない。既定は CBT。 */
const EXAM_TABS = [
  { key: "CBT", label: "CBT" },
  { key: "KOKUSHI", label: "医師国家試験" },
  { key: "", label: "すべて" },
];

/** ソロモード: 分野別の演習リスト（旧 Home の分野別リストを移設）。 */
export default function Solo() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const examType = searchParams.get("exam_type") ?? "CBT";
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setProgress(null);
    setError(null);
    api
      .progress(examType || undefined)
      .then((data) => {
        if (!cancelled) setProgress(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [examType]);

  const totalQuestions = progress?.reduce((sum, p) => sum + p.total, 0) ?? 0;

  return (
    <div className="screen">
      <h2>ソロモード：分野別演習</h2>

      <div className="filter-chip-row">
        {EXAM_TABS.map((tab) => (
          <button
            key={tab.key || "all"}
            className={`filter-chip${examType === tab.key ? " active" : ""}`}
            onClick={() =>
              setSearchParams(tab.key ? { exam_type: tab.key } : {}, { replace: true })
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {!progress && !error && <p>読み込み中...</p>}
      {progress?.length === 0 && <p>この試験種別の問題はまだありません。</p>}
      {progress?.length > 0 && (
        <p className="course-count">
          {progress.length}分野 / {totalQuestions}問
        </p>
      )}

      <div className="course-list">
        {progress?.map((p, i) => (
          <button
            key={p.category}
            className="course-row"
            onClick={() =>
              navigate(
                `/solo/${encodeURIComponent(p.category)}${
                  examType ? `?exam_type=${encodeURIComponent(examType)}` : ""
                }`,
              )
            }
          >
            <div className="course-row-top">
              <span className="course-letter">{String.fromCharCode(65 + i)}</span>
              <span className="course-name">
                {p.category} <span className="course-count">({p.total})</span>
              </span>
              <span className="course-remaining">残り{p.remaining}問</span>
            </div>
            <ProgressBar counts={p.counts} total={p.total} />
          </button>
        ))}
      </div>
    </div>
  );
}
