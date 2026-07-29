import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";

/** 模試結果: 順位・偏差値・分野別スコア（バー表示）・全問見直し。 */
export default function Result() {
  const { examId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.examResult(examId).then(setData).catch((e) => setError(e.message));
  }, [examId]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>読み込み中...</p>;

  if (data.status === "grading") {
    return (
      <div className="screen">
        <h2>模試結果</h2>
        <div className="empty-card">{data.message}</div>
        <Link to="/exams" className="back-link">
          ← 模試一覧へ
        </Link>
      </div>
    );
  }

  return (
    <div className="screen">
      <h2>{data.title} 結果</h2>

      <div className="summary-card">
        <div className="summary-pct">
          <span className="summary-pct-value">
            {data.score}
            <span style={{ fontSize: 14 }}>/{data.max_score}</span>
          </span>
          <span className="summary-pct-label">得点</span>
        </div>
        <div className="summary-ranks">
          <div className="rank-stat">
            <span className="rank-label">全国順位</span>
            <span className="rank-value">
              {data.rank}位 / {data.out_of}人中（上位{(100 - data.percentile).toFixed(1)}%）
            </span>
          </div>
          <div className="rank-stat">
            <span className="rank-label">学内順位</span>
            <span className="rank-value">
              {data.university_rank ? `${data.university_rank}位` : "―"}
            </span>
          </div>
          <div className="rank-stat">
            <span className="rank-label">偏差値</span>
            <span className="rank-value">{data.deviation_score}</span>
          </div>
        </div>
      </div>

      <h3 className="exam-section-heading">分野別スコア</h3>
      <div className="mypage-card">
        {Object.entries(data.section_scores).map(([area, rate]) => (
          <div key={area} className="exam-section-row">
            <span className="exam-section-name">{area}</span>
            <div className="exam-section-bar">
              <div className="exam-section-fill" style={{ width: `${rate * 100}%` }} />
            </div>
            <span className="exam-section-rate">{Math.round(rate * 100)}%</span>
          </div>
        ))}
      </div>

      <h3 className="exam-section-heading">見直し</h3>
      {data.review.map((row) => {
        const correct = row.my_choice === row.correct_choice_key;
        return (
          <div key={row.question_id} className="mypage-card exam-review-card">
            <p className="exam-review-head">
              <span className={correct ? "verdict correct" : "verdict incorrect"}>
                {correct ? "○" : "✕"}
              </span>{" "}
              第{row.order}問
            </p>
            <p className="exam-review-text">{row.question_text}</p>
            <p className="exam-review-answer">
              あなたの解答: {row.my_choice || "未解答"} ／ 正解: {row.correct_choice_key}
            </p>
            <p className="explanation">{row.explanation}</p>
          </div>
        );
      })}

      <Link to="/exams" className="back-link">
        ← 模試一覧へ
      </Link>
    </div>
  );
}
