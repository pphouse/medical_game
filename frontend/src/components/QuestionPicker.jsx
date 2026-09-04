import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { getCategoryTheme } from "../categoryTheme";
import { shuffled } from "../shuffle";

// 理解できている側から並べる（◎→未演習）。復習デッキの評価フィルタや
// 解答後の5段階ボタンと向きをそろえる。
const FILTERS = [
  { key: "all", label: "すべて" },
  { key: "double_circle", label: "◎" },
  { key: "circle", label: "○" },
  { key: "triangle", label: "△" },
  { key: "cross", label: "✕" },
  { key: "unstudied", label: "未演習" },
];

/** ◎○△✕未演習の5段階。初期状態は全部が選択済み。 */
const MASTERY_KEYS = FILTERS.filter((f) => f.key !== "all").map((f) => f.key);

const MASTERY_ICON = {
  double_circle: "◎",
  circle: "○",
  triangle: "△",
  cross: "✕",
  unstudied: "－",
};

const DIFFICULTY_LABEL = { 1: "易", 2: "標準", 3: "難" };

// backend の QuestionReport.Reason と対応（値がずれると 400 になる）。
const REPORT_REASONS = [
  { key: "wrong_answer", label: "正解が誤っている" },
  { key: "ambiguous", label: "設問が曖昧" },
  { key: "typo", label: "誤字脱字" },
  { key: "inappropriate", label: "不適切な内容" },
  { key: "other", label: "その他" },
];

/** 一覧の下に置く「間違いの報告」フォーム。管理者の通報一覧に届く。
 * 通報が3件付いた問題は自動で出題から外れる（サーバ側の仕組み）。 */
function ReportForm({ questions }) {
  const [open, setOpen] = useState(false);
  const [questionId, setQuestionId] = useState("");
  const [reason, setReason] = useState(REPORT_REASONS[0].key);
  const [detail, setDetail] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!questionId) return;
    setSending(true);
    setError(null);
    try {
      await api.reportQuestion(Number(questionId), { reason, detail: detail.trim() });
      setDone(true);
      setDetail("");
      setQuestionId("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  if (!open) {
    return (
      <button className="report-link" onClick={() => setOpen(true)}>
        問題に間違いを見つけたら報告する
      </button>
    );
  }

  return (
    <form className="mypage-card report-form" onSubmit={handleSubmit}>
      <h3 className="exam-section-heading" style={{ marginTop: 0 }}>
        間違いの報告
      </h3>
      <p className="exam-meta">
        気づいた点を管理者に送れます。内容を確認して修正します。
      </p>

      {done && <p className="report-done">報告しました。ご協力ありがとうございます。</p>}

      <label className="profile-field">
        <span className="profile-field-label">対象の問題</span>
        <select value={questionId} onChange={(e) => setQuestionId(e.target.value)} required>
          <option value="">選択してください</option>
          {questions.map((q, i) => (
            <option key={q.id} value={q.id}>
              第{i + 1}問: {(q.case_stem || q.question_text || "").slice(0, 30)}
            </option>
          ))}
        </select>
      </label>

      <label className="profile-field">
        <span className="profile-field-label">種類</span>
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          {REPORT_REASONS.map((r) => (
            <option key={r.key} value={r.key}>
              {r.label}
            </option>
          ))}
        </select>
      </label>

      <label className="profile-field">
        <span className="profile-field-label">詳細（任意）</span>
        <textarea
          rows={3}
          value={detail}
          maxLength={1000}
          placeholder="どこがどう間違っているか、分かる範囲で教えてください。"
          onChange={(e) => setDetail(e.target.value)}
        />
      </label>

      {error && <p className="error">{error}</p>}

      <div className="profile-editor-actions">
        <button type="button" className="toolbar-btn" onClick={() => setOpen(false)}>
          閉じる
        </button>
        <button type="submit" className="cta-button" disabled={sending || !questionId}>
          {sending ? "送信中..." : "報告を送る"}
        </button>
      </div>
    </form>
  );
}

function formatResponseTime(ms) {
  if (ms == null) return null;
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}'${String(s).padStart(2, "0")}"`;
}

function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return `${String(d.getFullYear()).slice(2)}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

export default function QuestionPicker() {
  const { category } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // 同じ分野名が CBT と国試の両方にあるので、一覧で選んだ試験種別を持ち回る。
  const examType = searchParams.get("exam_type") ?? "";
  const soloUrl = `/solo${examType ? `?exam_type=${encodeURIComponent(examType)}` : ""}`;
  // 演習中の「戻る」はこの問題一覧に戻す（分野一覧まで戻すと、続けて別の
  // 問題を解きたいときに毎回選び直しになるため）。
  const pickerUrl = `/solo/${encodeURIComponent(category)}${
    examType ? `?exam_type=${encodeURIComponent(examType)}` : ""
  }`;
  const theme = getCategoryTheme(category);
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState(null);
  // 初期状態は5段階すべてが選択済み。チップを押すとその段階だけを外せる
  // （複数選択可）。「すべて」は全選択⇔全解除のトグル。
  const [selected, setSelected] = useState(() => new Set(MASTERY_KEYS));

  useEffect(() => {
    api
      .questions(category, examType ? { exam_type: examType } : {})
      .then(setQuestions)
      .catch((e) => setError(e.message));
  }, [category, examType]);

  if (error) return <p className="error">{error}</p>;
  if (!questions) return <p>読み込み中...</p>;

  const counts = { all: questions.length };
  for (const f of FILTERS) {
    if (f.key === "all") continue;
    counts[f.key] = questions.filter((q) => q.mastery_level === f.key).length;
  }

  const allSelected = selected.size === MASTERY_KEYS.length;
  const filtered = questions.filter((q) => selected.has(q.mastery_level));

  function toggleFilter(key) {
    if (key === "all") {
      setSelected(allSelected ? new Set() : new Set(MASTERY_KEYS));
      return;
    }
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="screen">
      <button className="back-link" onClick={() => navigate(soloUrl)}>
        ← 分野一覧に戻る
      </button>
      {/* 分野ごとの配色（categoryTheme）で見出しを塗る。演習中の結果画面や
          分野一覧と同じ色なので、どの分野にいるか一目で分かる。 */}
      <div className={`picker-heading theme-${theme.key}`}>
        <span className="picker-heading-letter">{theme.letter}</span>
        <span className="picker-heading-text">
          <span className="picker-heading-category">{category}</span>
          <span className="picker-heading-sub">どの問題を解くか選ぶ</span>
        </span>
      </div>

      <div className="filter-chip-row">
        {FILTERS.map((f) => {
          const active = f.key === "all" ? allSelected : selected.has(f.key);
          return (
            <button
              key={f.key}
              className={`filter-chip${active ? " active" : ""}`}
              onClick={() => toggleFilter(f.key)}
            >
              {f.label}
              <span className="filter-chip-count">{counts[f.key]}</span>
            </button>
          );
        })}
      </div>

      <div className="start-button-row">
        <button
          className="cta-button"
          disabled={filtered.length === 0}
          onClick={() =>
            navigate("/quiz", {
              state: { title: `分野別演習: ${category}`, questions: filtered, backTo: pickerUrl },
            })
          }
        >
          演習を始める ▶
        </button>
        <button
          className="cta-button cta-button-secondary"
          disabled={filtered.length === 0}
          onClick={() =>
            navigate("/quiz", {
              state: {
                title: `分野別演習: ${category}`,
                questions: shuffled(filtered),
                backTo: pickerUrl,
              },
            })
          }
        >
          <span className="shuffle-icon">⇄</span> シャッフルして始める ▶
        </button>
      </div>

      <p className="course-count">
        {selected.size === 0
          ? "上のボタンで出題したい評価（◎○△✕未演習）を選んでください。"
          : `${questions.length}問中 ${filtered.length}問を表示`}
      </p>

      <div className="question-list">
        {filtered.map((q, i) => {
          const responseTime = formatResponseTime(q.last_response_time_ms);
          const answeredDate = formatDate(q.last_answered_at);
          return (
            <button
              key={q.id}
              className="question-row question-row-detailed"
              onClick={() =>
                navigate("/quiz", {
                  state: {
                    title: `分野別演習: ${category}`,
                    questions: filtered,
                    backTo: pickerUrl,
                    startIndex: i,
                  },
                })
              }
            >
              <div className="question-row-main">
                <span className="question-row-no">{i + 1}</span>
                <span className="question-row-stem">
                  {q.case_stem || q.question_text || "（本文なし）"}
                </span>
              </div>
              <div className="question-row-meta">
                <span className="question-row-meta-line">
                  {q.category}
                  {q.topic && ` ＞ ${q.topic}`}
                </span>
                <span className="question-row-meta-line">
                  <span>
                    国試正答率：{q.correct_rate == null ? "集計中" : `${q.correct_rate}%`}
                  </span>
                  <span className="question-row-meta-sep" />
                  <span>結果：</span>
                  {q.mastery_level === "unstudied" ? (
                    <span>－</span>
                  ) : (
                    <span className={`question-row-mastery mastery-${q.mastery_level}`}>
                      {MASTERY_ICON[q.mastery_level]}
                    </span>
                  )}
                </span>
                <span className="question-row-meta-line">
                  <span>解答時間：{responseTime ?? "－"}</span>
                  <span className="question-row-meta-sep" />
                  <span>演習日：{answeredDate ?? "－"}</span>
                </span>
              </div>
              <span className="question-row-difficulty">{DIFFICULTY_LABEL[q.difficulty]}</span>
            </button>
          );
        })}
      </div>

      <ReportForm questions={filtered} />
    </div>
  );
}
