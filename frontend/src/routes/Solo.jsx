import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import ProgressBar from "../components/ProgressBar";

/** ソロモード: 分野別の演習リスト（旧 Home の分野別リストを移設）。 */
export default function Solo() {
  const navigate = useNavigate();
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.progress().then(setProgress).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="screen">
      <h2>ソロモード：分野別演習</h2>

      {error && <p className="error">{error}</p>}
      {!progress && !error && <p>読み込み中...</p>}

      <div className="course-list">
        {progress?.map((p, i) => (
          <button
            key={p.category}
            className="course-row"
            onClick={() => navigate(`/solo/${encodeURIComponent(p.category)}`)}
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
