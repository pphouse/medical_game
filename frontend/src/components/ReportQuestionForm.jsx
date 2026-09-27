import { useEffect, useState } from "react";
import { api } from "../api";

// 演習中に出す報告の選択肢。管理画面の通報一覧と同じ値（サーバの
// QuestionReport.Reason）。ここは解いている最中に迷わず選べるよう3つに絞り、
// 細かい区別は自由記述で受ける。
const REASONS = [
  { key: "wrong_question", label: "問題文が間違っている" },
  { key: "wrong_answer", label: "解答が間違っている" },
  { key: "other", label: "その他" },
];

/** 問題の下に置く「間違い・不具合を報告」フォーム。
 *
 * 文字を押すと開き、送信すると閉じて元の問題の画面に戻る。届いた報告は
 * 管理画面の通報一覧（/admin/reports）から確認できる。同じ問題に3人から
 * 報告が付くと、その問題は自動で出題から外れる（サーバ側の仕組み）。 */
export default function ReportQuestionForm({ questionId }) {
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState(() => new Set());
  const [detail, setDetail] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  // 次の問題に進んだら、前の問題で開いていた内容は持ち越さない。
  useEffect(() => {
    setOpen(false);
    setChecked(new Set());
    setDetail("");
    setError(null);
    setDone(false);
  }, [questionId]);

  function toggle(key) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!checked.size || sending) return;
    setSending(true);
    setError(null);
    try {
      await api.reportQuestion(questionId, {
        reasons: [...checked],
        detail: detail.trim(),
      });
      // 送ったら閉じて、元の問題の画面に戻す。
      setOpen(false);
      setChecked(new Set());
      setDetail("");
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  if (done && !open) {
    return <p className="report-done">報告しました。ご協力ありがとうございます。</p>;
  }

  if (!open) {
    return (
      <button type="button" className="report-open" onClick={() => setOpen(true)}>
        間違い・不具合を報告
      </button>
    );
  }

  return (
    <form className="report-form" onSubmit={handleSubmit}>
      <p className="report-form-title">間違い・不具合を報告</p>
      <div className="report-reasons">
        {REASONS.map((r) => (
          <label key={r.key} className="report-reason">
            <input
              type="checkbox"
              checked={checked.has(r.key)}
              onChange={() => toggle(r.key)}
            />
            <span>{r.label}</span>
          </label>
        ))}
      </div>
      <textarea
        className="report-detail"
        rows={4}
        placeholder="気づいたことがあれば書いてください（任意）"
        value={detail}
        onChange={(e) => setDetail(e.target.value)}
      />
      {error && <p className="error">{error}</p>}
      <div className="report-actions">
        <button type="button" className="toolbar-btn" onClick={() => setOpen(false)}>
          キャンセル
        </button>
        <button type="submit" className="cta-button" disabled={!checked.size || sending}>
          {sending ? "送信中..." : "フォームを送信する"}
        </button>
      </div>
    </form>
  );
}
