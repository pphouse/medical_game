import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useProfile } from "../context/ProfileContext";
import { shuffled } from "../shuffle";

// 演習の入口。CBT / 国試は問題バンク全体から、模試復習 / 対戦復習は
// 「自分がそこで解いたことのある問題」から出題する（模試や対戦を重ねる
// たびに対象が増えていく）。
const TABS = [
  { key: "CBT", label: "CBT", examType: "CBT" },
  { key: "KOKUSHI", label: "医師国家試験", examType: "KOKUSHI" },
  { key: "mock", label: "模試復習", source: "mock" },
  { key: "battle", label: "対戦復習", source: "battle" },
];

// CBT と国試は分野の切り方が違ううえ問題数も桁が近いので、混ぜて一覧に
// すると目的の科目を探せない（問題演習画面と同じ理由・同じ既定値）。
const EXAM_TABS = [
  { key: "CBT", label: "CBT" },
  { key: "KOKUSHI", label: "医師国家試験" },
  { key: "", label: "すべて" },
];

// 理解できている側から並べる（◎→未演習）。他の画面の5段階表示や
// 問題一覧の評価チップと向きをそろえるため。
const MASTERY_FILTERS = [
  { key: "double_circle", label: "◎" },
  { key: "circle", label: "○" },
  { key: "triangle", label: "△" },
  { key: "cross", label: "✕" },
  { key: "unstudied", label: "未演習" },
];

const ATTEMPT_FILTERS = [
  { key: "1", label: "1回" },
  { key: "2", label: "2回" },
  { key: "3plus", label: "3回以上" },
];

const EMPTY_SOURCE_MESSAGE = {
  mock: "まだ模試で解いた問題がありません。模試を受けると、その問題がここに追加されます。",
  battle: "まだ対戦で解いた問題がありません。対戦すると、その問題がここに追加されます。",
};

function toggle(set, key) {
  const next = new Set(set);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

/** 科目・評価・演習回数を掛け合わせて演習セットを作る。
 * 空集合は「絞り込まない」= 全部が対象。
 *
 * `fixedExamType` を渡すとその試験種別に固定し、試験種別の選択欄は出さない
 * （CBT / 国試タブはタブ自体が試験種別なので）。`source` を渡すと、その
 * 文脈（模試・対戦）で自分が解いたことのある問題だけが対象になる。
 * `mockExam` を渡すと、その1回の模試で出題された問題だけが対象になる。 */
function FilteredPractice({
  onStartSession,
  fixedExamType = null,
  source = null,
  mockExam = null,
}) {
  const { profile } = useProfile();
  // null は「まだ手動で選んでいない」＝マイページの設定（未選択なら学年から
  // 決まる resolved_exam_type）に従う。一度選んだらそれ以降はそちらを優先。
  const [examTypeOverride, setExamTypeOverride] = useState(null);
  const examType =
    fixedExamType ?? examTypeOverride ?? profile?.resolved_exam_type ?? "CBT";
  const [selectedCategories, setSelectedCategories] = useState(new Set());
  const [selectedMastery, setSelectedMastery] = useState(new Set());
  const [selectedAttempts, setSelectedAttempts] = useState(new Set());
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // 試験種別で分野の切り方が違うので、切り替えたら科目の絞り込みは
  // 一旦リセットする（前の試験種別にしかない科目が残ると混乱するため）。
  useEffect(() => {
    setSelectedCategories(new Set());
  }, [examType, source, mockExam]);

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    api
      .reviewFilter({
        categories: [...selectedCategories],
        mastery: [...selectedMastery],
        attempts: [...selectedAttempts],
        examType,
        source,
        mockExam,
      })
      .then((data) => !cancelled && setResult(data))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [selectedCategories, selectedMastery, selectedAttempts, examType, source, mockExam]);

  if (error) return <p className="error">{error}</p>;
  if (!result) return <p>読み込み中...</p>;

  const categories = result.available_categories ?? [];
  const count = result.count ?? 0;

  // 模試・対戦の復習は、まだ一度も解いていないと対象が空になる。絞り込みの
  // 結果ゼロなのか、そもそも履歴が無いのかを取り違えないよう文言を分ける。
  if (source && !mockExam && categories.length === 0 && selectedCategories.size === 0) {
    return <p>{EMPTY_SOURCE_MESSAGE[source]}</p>;
  }

  return (
    <>
      {!fixedExamType && (
        <div className="filter-group">
          <span className="filter-group-title">試験種別</span>
          <div className="filter-chip-row">
            {EXAM_TABS.map((t) => (
              <button
                key={t.key || "all"}
                className={`filter-chip${examType === t.key ? " active" : ""}`}
                onClick={() => setExamTypeOverride(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="filter-group">
        <div className="filter-group-head">
          <span className="filter-group-title">科目</span>
          <div className="filter-group-actions">
            <button onClick={() => setSelectedCategories(new Set(categories))}>
              全科目チェック
            </button>
            <button onClick={() => setSelectedCategories(new Set())}>全科目クリア</button>
          </div>
        </div>
        <div className="filter-chip-row">
          {categories.map((c) => (
            <button
              key={c}
              className={`filter-chip${selectedCategories.has(c) ? " active" : ""}`}
              onClick={() => setSelectedCategories((s) => toggle(s, c))}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-group">
        <span className="filter-group-title">評価</span>
        <div className="filter-chip-row">
          {MASTERY_FILTERS.map((m) => (
            <button
              key={m.key}
              className={`filter-chip${selectedMastery.has(m.key) ? " active" : ""}`}
              onClick={() => setSelectedMastery((s) => toggle(s, m.key))}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-group">
        <span className="filter-group-title">演習回数</span>
        <div className="filter-chip-row">
          {ATTEMPT_FILTERS.map((a) => (
            <button
              key={a.key}
              className={`filter-chip${selectedAttempts.has(a.key) ? " active" : ""}`}
              onClick={() => setSelectedAttempts((s) => toggle(s, a.key))}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>

      <div className="start-button-row">
        <button
          className="cta-button"
          disabled={count === 0}
          onClick={() =>
            onStartSession({
              title: "演習問題",
              questions: result.results,
              context: "review",
            })
          }
        >
          {count === 0 ? "条件に合う問題がありません" : `演習を始める（${count}問）`}
        </button>
        <button
          className="cta-button cta-button-secondary"
          disabled={count === 0}
          onClick={() =>
            onStartSession({
              title: "演習問題",
              questions: shuffled(result.results),
              context: "review",
            })
          }
        >
          <span className="shuffle-icon">⇄</span> シャッフルして始める ▶
        </button>
      </div>

      {result.truncated && (
        <p className="course-count">
          該当が多いため、先頭{result.results.length}問を出題します。条件を絞ると狙った範囲だけ解けます。
        </p>
      )}
    </>
  );
}

const KIND_LABEL = {
  monthly: "月次実力テスト",
  large: "国試模試",
  cbt_once: "CBT模試",
};

/** 復習する模試を選ぶ。先頭が「すべての模試」で、以下は1回ずつ。 */
function MockExamPicker({ selected, onSelect }) {
  const [rows, setRows] = useState(null);

  useEffect(() => {
    api.rankingExams().then(setRows).catch(() => setRows([]));
  }, []);

  const taken = (rows ?? []).filter((r) => r.submitted !== false);

  return (
    <div className="filter-group">
      <span className="filter-group-title">復習する模試</span>
      <div className="course-list">
        <button
          className={`course-row mock-pick${selected === null ? " active" : ""}`}
          onClick={() => onSelect(null)}
        >
          <div className="course-row-top">
            <span className="course-name">すべての模試を復習</span>
            <span className="course-count">
              {taken.length ? `${taken.length}回ぶん` : ""}
            </span>
          </div>
        </button>
        {taken.map((r) => (
          <button
            key={r.mock_exam_id}
            className={`course-row mock-pick${selected === r.mock_exam_id ? " active" : ""}`}
            onClick={() => onSelect(r.mock_exam_id)}
          >
            <div className="course-row-top">
              <span className="course-name">
                {r.title}
                <span className="course-count"> {KIND_LABEL[r.kind] ?? ""}</span>
              </span>
              <span className="course-remaining">
                {new Date(r.start_at).toLocaleDateString("ja-JP")}
              </span>
            </div>
          </button>
        ))}
      </div>
      {rows && taken.length === 0 && (
        <p className="exam-meta">
          まだ受験した模試がありません。模試を受けると、ここで1回ずつ復習できます。
        </p>
      )}
    </div>
  );
}

export default function ReviewDeck() {
  const navigate = useNavigate();
  const onStartSession = (session) =>
    navigate("/quiz", { state: { ...session, backTo: "/review" } });
  const { profile } = useProfile();
  const [tabKey, setTabKey] = useState(null);
  // null は「すべての模試」。模試を選ぶとその1回だけが対象になる。
  const [mockExam, setMockExam] = useState(null);
  // 既定はマイページの設定（未選択なら学年から決まる resolved_exam_type）。
  const active = TABS.find((t) => t.key === tabKey)
    ?? TABS.find((t) => t.key === (profile?.resolved_exam_type ?? "CBT"))
    ?? TABS[0];

  return (
    <div className="screen">
      <h2>総合演習</h2>
      <div className="filter-chip-row">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`filter-chip${active.key === t.key ? " active" : ""}`}
            onClick={() => setTabKey(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {active.key === "mock" && (
        <MockExamPicker selected={mockExam} onSelect={setMockExam} />
      )}

      <FilteredPractice
        key={`${active.key}-${active.key === "mock" ? mockExam : ""}`}
        onStartSession={onStartSession}
        fixedExamType={active.examType ?? null}
        source={active.source ?? null}
        mockExam={active.key === "mock" ? mockExam : null}
      />
    </div>
  );
}
