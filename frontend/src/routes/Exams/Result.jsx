import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";

/** 模試結果: 順位・偏差値・分野別スコア（バー表示）・全問見直し。
 * kind に応じて追加のパネルを出す:
 *   weekly/monthly: 獲得ポイント・現在のランク
 *   large         : 分野別偏差値・得点分布
 *   cbt_once      : 予想IRT（θ・偏差値相当スケール）
 */
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

  const hasDeviation = data.deviation_score != null;
  const hasDistribution = Boolean(data.score_distribution?.buckets?.length);
  const hasSectionDeviation = Object.keys(data.section_deviation_scores || {}).length > 0;

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
          {data.rank != null && (
            <div className="rank-stat">
              <span className="rank-label">全国順位</span>
              <span className="rank-value">
                {data.rank}位 / {data.out_of}人中
                {data.percentile != null && `（上位${(100 - data.percentile).toFixed(1)}%）`}
              </span>
            </div>
          )}
          {data.university_rank != null && (
            <div className="rank-stat">
              <span className="rank-label">学内順位</span>
              <span className="rank-value">{data.university_rank}位</span>
            </div>
          )}
          {hasDeviation && (
            <div className="rank-stat">
              <span className="rank-label">偏差値</span>
              <span className="rank-value">{data.deviation_score}</span>
            </div>
          )}
        </div>
      </div>

      {data.points_delta != null && (
        <div className="mypage-card">
          <span className="tier-badge">
            獲得ポイント {data.points_delta >= 0 ? "+" : ""}
            {data.points_delta}
            {data.tier_after && ` ・ 現在 ${data.points_after}pt（${data.tier_after}ランク）`}
          </span>
        </div>
      )}

      {data.irt_scaled_score != null && (
        <div className="mypage-card">
          <h3 className="exam-section-heading" style={{ marginTop: 0 }}>
            予想IRT
          </h3>
          <p className="exam-meta">
            能力値 θ = {data.irt_theta} ／ 偏差値相当スケール = <b>{data.irt_scaled_score}</b>
          </p>
          <p className="exam-meta">
            過去の解答傾向から較正した項目パラメータをもとに推定した参考値です。
          </p>
        </div>
      )}

      <h3 className="exam-section-heading">分野別スコア</h3>
      <div className="mypage-card">
        {Object.entries(data.section_scores).map(([area, rate]) => (
          <div key={area} className="exam-section-row">
            <span className="exam-section-name">{area}</span>
            <div className="exam-section-bar">
              <div className="exam-section-fill" style={{ width: `${rate * 100}%` }} />
            </div>
            <span className="exam-section-rate">
              {Math.round(rate * 100)}%
              {hasSectionDeviation && data.section_deviation_scores[area] != null && (
                <> （偏差値{data.section_deviation_scores[area]}）</>
              )}
            </span>
          </div>
        ))}
      </div>

      {hasDistribution && (
        <>
          <h3 className="exam-section-heading">得点分布</h3>
          <div className="mypage-card">
            <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 90 }}>
              {data.score_distribution.buckets.map((count, i) => {
                const max = Math.max(...data.score_distribution.buckets, 1);
                const isMe = i === data.score_distribution.my_bucket;
                return (
                  <div
                    key={i}
                    style={{
                      flex: 1,
                      height: `${Math.max(6, (count / max) * 100)}%`,
                      borderRadius: "3px 3px 0 0",
                      background: isMe ? "var(--accent-grad)" : "var(--border)",
                    }}
                  />
                );
              })}
            </div>
            <p className="exam-meta">色付きの棒があなたの得点帯です。</p>
          </div>
        </>
      )}

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
