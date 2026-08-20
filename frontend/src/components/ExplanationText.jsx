/** 解説文を選択肢ごと・段落ごとに改行して表示する。 */
export default function ExplanationText({ text }) {
  if (!text) return null;
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  return (
    <div className="explanation">
      {lines.map((line, i) => (
        <p key={i}>{line}</p>
      ))}
    </div>
  );
}
