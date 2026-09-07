/** 選択肢ごとの解説。正解・誤答それぞれが「なぜそうなのか」を選択肢の
 * 並びのまま見せる。解説の無い選択肢は行ごと出さない。 */
export default function ChoiceNotes({ choices, notes, correctKey, myKey }) {
  const entries = (choices ?? []).filter((c) => notes?.[c.key]);
  if (!entries.length) return null;

  return (
    <ul className="choice-note-list">
      {entries.map((c) => (
        <li
          key={c.key}
          className={`choice-note-row${c.key === correctKey ? " correct" : ""}${
            c.key === myKey && c.key !== correctKey ? " incorrect" : ""
          }`}
        >
          <span className="choice-key">{c.key}</span>
          <span className="choice-note-text">
            <span className="choice-note-label">{c.text}</span>
            <span className="choice-note">{notes[c.key]}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
