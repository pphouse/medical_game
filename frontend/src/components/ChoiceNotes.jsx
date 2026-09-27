/** 見直し用の選択肢一覧。
 *
 * 正解は緑、自分が選んで外した選択肢は赤で示す（自分の解答が正解なら緑の
 * まま）。選択肢ごとの解説があれば、その選択肢の下に添える。 */
export default function ChoiceNotes({ choices, notes, correctKey, myKey }) {
  if (!choices?.length) return null;

  return (
    <ul className="choice-note-list">
      {choices.map((c) => {
        const isCorrect = c.key === correctKey;
        const isMyMistake = c.key === myKey && !isCorrect;
        const note = notes?.[c.key];
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
              {note && <span className="choice-note">{note}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
