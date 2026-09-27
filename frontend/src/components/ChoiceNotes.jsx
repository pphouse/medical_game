/** 見直し画面の選択肢一覧。
 *
 * 正解は緑、自分が選んで外した選択肢は赤で示す（自分の解答が正解なら緑の
 * まま）。選択肢ごとの解説はここには出さず、解説文の中に並べる
 * （ExplanationText の notes）。同じ選択肢を2回読ませないため。 */
export default function ChoiceNotes({ choices, correctKey, myKey }) {
  if (!choices?.length) return null;

  return (
    <ul className="choice-note-list">
      {choices.map((c) => {
        const isCorrect = c.key === correctKey;
        const isMyMistake = c.key === myKey && !isCorrect;
        return (
          <li
            key={c.key}
            className={`choice-note-row${isCorrect ? " correct" : ""}${
              isMyMistake ? " incorrect" : ""
            }`}
          >
            <span className="choice-key">{c.key}</span>
            <span className="choice-note-text">
              <span className="choice-note-label">
                {c.text}
                {isCorrect && <span className="choice-note-tag">正解</span>}
                {c.key === myKey && <span className="choice-note-tag">あなたの解答</span>}
              </span>
            </span>
            {/* 間違えた選択肢だけ印を出す（色だけに頼らないため）。 */}
            {isMyMistake && (
              <span className="choice-mark" aria-label="あなたの誤答">
                ❌
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
