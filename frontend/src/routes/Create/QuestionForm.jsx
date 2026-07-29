import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import QuizScreen from "../../components/QuizScreen";

const KEYS = ["A", "B", "C", "D", "E"];
const EMPTY = {
  category: "",
  topic: "",
  exam_type: "CBT",
  difficulty: 2,
  question_text: "",
  choices: KEYS.map((k) => ({ key: k, text: "" })),
  correct_choice_key: "A",
  explanation: "",
  visibility: "public",
};

/** 問題作成/編集フォーム + 既存 QuizScreen を再利用したプレビュー (spec フェーズ7). */
export default function QuestionForm() {
  const { questionId } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [answeredLocked, setAnsweredLocked] = useState(false);
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!questionId) return;
    api
      .myQuestions()
      .then((rows) => {
        const target = rows.find((q) => String(q.id) === questionId);
        if (!target) throw new Error("問題が見つかりません。");
        setForm(target);
        setAnsweredLocked(target.answer_count > 0);
      })
      .catch((e) => setError(e.message));
  }, [questionId]);

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateChoice(index, text) {
    setForm((prev) => ({
      ...prev,
      choices: prev.choices.map((c, i) => (i === index ? { ...c, text } : c)),
    }));
  }

  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      if (questionId) {
        const payload = answeredLocked ? { explanation: form.explanation } : form;
        await api.updateQuestion(questionId, payload);
      } else {
        await api.createQuestion(form);
      }
      navigate("/create");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (preview) {
    return (
      <QuizScreen
        title="プレビュー"
        questions={[{ ...form, id: 0, correct_rate: null }]}
        onBack={() => setPreview(false)}
        previewMode
      />
    );
  }

  return (
    <div className="screen">
      <button className="back-link" onClick={() => navigate("/create")}>
        ← 自作問題一覧へ
      </button>
      <h2>{questionId ? "問題を編集" : "問題をつくる"}</h2>
      {answeredLocked && (
        <div className="empty-card">
          この問題には解答履歴があるため、本文は編集できません（解説の追記のみ可能です）。
        </div>
      )}
      {error && <p className="error">{error}</p>}

      <div className="mypage-card create-form">
        <label className="auth-field">
          分野（例: 循環器）
          <input
            value={form.category}
            onChange={(e) => update("category", e.target.value)}
            disabled={answeredLocked}
          />
        </label>
        <label className="auth-field">
          疾患・トピック（任意）
          <input
            value={form.topic}
            onChange={(e) => update("topic", e.target.value)}
            disabled={answeredLocked}
          />
        </label>
        <label className="auth-field">
          設問文
          <textarea
            rows={4}
            value={form.question_text}
            onChange={(e) => update("question_text", e.target.value)}
            disabled={answeredLocked}
          />
        </label>

        {form.choices.map((choice, i) => (
          <label key={choice.key} className="auth-field create-choice-row">
            <span className="create-choice-head">
              <input
                type="radio"
                name="correct"
                checked={form.correct_choice_key === choice.key}
                onChange={() => update("correct_choice_key", choice.key)}
                disabled={answeredLocked}
              />
              選択肢{choice.key}（正解にする場合はチェック）
            </span>
            <input
              value={choice.text}
              onChange={(e) => updateChoice(i, e.target.value)}
              disabled={answeredLocked}
            />
          </label>
        ))}

        <label className="auth-field">
          解説
          <textarea
            rows={4}
            value={form.explanation}
            onChange={(e) => update("explanation", e.target.value)}
          />
        </label>

        <label className="auth-field">
          公開範囲
          <select
            value={form.visibility}
            onChange={(e) => update("visibility", e.target.value)}
            className="notification-select"
            disabled={answeredLocked}
          >
            <option value="public">公開（全ユーザー）</option>
            <option value="university_only">学内限定（あなたの所属大学のみ）</option>
          </select>
        </label>

        <div className="create-actions">
          <button className="toolbar-btn" onClick={() => setPreview(true)}>
            プレビュー
          </button>
          <button className="cta-button" onClick={handleSave} disabled={busy}>
            {questionId ? "保存する" : "下書きとして保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
