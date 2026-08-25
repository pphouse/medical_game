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
  status: "pending",
};

/** 管理者による問題の新規作成・編集。
 *
 * ユーザー投稿用の QuestionForm と違い status を直接指定できる。
 * 解答履歴のある問題も編集できるが、過去の正誤の意味が変わるので警告を出す。 */
export default function AdminQuestionEdit() {
  const { questionId } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [loaded, setLoaded] = useState(!questionId);
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // 分野は自由入力にしない。「循環器」と「循環器系」のように同じ分野が
  // 別名で増えるため、サーバが持つ正典から選ばせる。
  const [categories, setCategories] = useState([]);

  useEffect(() => {
    api
      .adminStats()
      .then((s) => setCategories(s.canonical_categories ?? []))
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!questionId) return;
    api
      .adminQuestion(questionId)
      .then((q) => {
        setForm(q);
        setLoaded(true);
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

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const payload = {
        category: form.category,
        topic: form.topic ?? "",
        exam_type: form.exam_type,
        difficulty: Number(form.difficulty),
        question_text: form.question_text,
        choices: form.choices,
        correct_choice_key: form.correct_choice_key,
        explanation: form.explanation,
        visibility: form.visibility,
        status: form.status,
      };
      if (questionId) await api.adminUpdateQuestion(questionId, payload);
      else await api.adminCreateQuestion(payload);
      navigate("/admin/questions");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm("この問題を削除します。取り消せません。よろしいですか？")) return;
    setBusy(true);
    try {
      await api.adminDeleteQuestion(questionId);
      navigate("/admin/questions");
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  if (!loaded) return <p className="screen">{error ? <span className="error">{error}</span> : "読み込み中..."}</p>;

  if (preview) {
    return (
      <QuizScreen
        title="プレビュー"
        questions={[{ ...form, id: form.id ?? 0 }]}
        onBack={() => setPreview(false)}
        previewMode
      />
    );
  }

  return (
    <div className="screen">
      <button className="back-link" onClick={() => navigate("/admin/questions")}>
        ← 問題一覧に戻る
      </button>
      <h2>{questionId ? "問題を編集" : "問題を新規作成"}</h2>

      {error && <p className="error">{error}</p>}
      {form.answer_count > 0 && (
        <p className="admin-warning">
          この問題にはすでに{form.answer_count}件の解答履歴があります。本文や正答を変えると、
          過去の正誤や正答率の意味が変わります。
        </p>
      )}

      <div className="create-form">
        <label>
          分野
          <select value={form.category} onChange={(e) => update("category", e.target.value)}>
            <option value="">（選択してください）</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
            {/* 正典に無い既存の値も、消えないように残して見せる */}
            {form.category && !categories.includes(form.category) && (
              <option value={form.category}>{form.category}（登録外）</option>
            )}
          </select>
        </label>
        <label>
          テーマ（任意）
          <input value={form.topic ?? ""} onChange={(e) => update("topic", e.target.value)} />
        </label>
        <label>
          試験種別
          <select value={form.exam_type} onChange={(e) => update("exam_type", e.target.value)}>
            <option value="CBT">CBT</option>
            <option value="KOKUSHI">医師国家試験</option>
          </select>
        </label>
        <label>
          難易度
          <select value={form.difficulty} onChange={(e) => update("difficulty", e.target.value)}>
            <option value={1}>易</option>
            <option value={2}>標準</option>
            <option value={3}>難</option>
          </select>
        </label>
        <label>
          公開状態
          <select value={form.status} onChange={(e) => update("status", e.target.value)}>
            <option value="draft">下書き</option>
            <option value="pending">審査待ち</option>
            <option value="published">公開</option>
            <option value="rejected">却下</option>
          </select>
        </label>
        <label>
          設問文
          <textarea
            rows={6}
            value={form.question_text}
            onChange={(e) => update("question_text", e.target.value)}
          />
        </label>

        <div className="create-choice-head">選択肢と正答</div>
        {form.choices.map((c, i) => (
          <div key={c.key} className="create-choice-row">
            <input
              type="radio"
              name="correct"
              checked={form.correct_choice_key === c.key}
              onChange={() => update("correct_choice_key", c.key)}
            />
            <span className="choice-key">{c.key}</span>
            <input value={c.text} onChange={(e) => updateChoice(i, e.target.value)} />
          </div>
        ))}

        <label>
          解説
          <textarea
            rows={8}
            value={form.explanation}
            onChange={(e) => update("explanation", e.target.value)}
          />
        </label>
      </div>

      <div className="create-actions">
        <button className="cta-button" disabled={busy} onClick={save}>
          {busy ? "保存中..." : "保存する"}
        </button>
        <button className="toolbar-btn" onClick={() => setPreview(true)}>
          プレビュー
        </button>
        {questionId && (
          <button className="toolbar-btn admin-danger" disabled={busy} onClick={remove}>
            削除
          </button>
        )}
      </div>
    </div>
  );
}
