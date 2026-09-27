/** 選択肢ごとの解説。
 *
 * 正解は緑、自分が選んで外した選択肢は赤で示す（自分の解答が正解なら緑の
 * まま）。解説があれば選択肢の下に添える。
 *
 * `onlyWhenNoted` を渡すと、解説が1つも無いときは何も描かない。演習画面の
 * ように選択肢そのものが上に並んでいる場所では、解説が無いのに同じ一覧を
 * 二度出しても意味がないため。模試や対戦の見直しではこれが選択肢一覧その
 * ものなので、渡さずに常に描く。 */
export default function ChoiceNotes({
  choices,
  notes,
  correctKey,
  myKey,
  onlyWhenNoted = false,
  heading = null,
}) {
  if (!choices?.length) return null;
  const hasNotes = choices.some((c) => notes?.[c.key]);
  if (onlyWhenNoted && !hasNotes) return null;

  return (
    <>
      {heading && hasNotes && <p className="choice-note-heading">{heading}</p>}
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
    </>
  );
}
