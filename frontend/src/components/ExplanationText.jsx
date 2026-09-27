const URL_RE = /(https?:\/\/[^\s）)]+)/g;

/** 出典表記と免責。解説本文とは役割が違うので、下にまとめて小さく出す。 */
function isNote(line) {
  return line.startsWith("※") || line.startsWith("出典") || /^https?:\/\//.test(line);
}

/** 生のURLを、短い文言のリンクに置き換える。
 *
 * 出典のURLは100字近くあり、そのまま出すと1段落を丸ごと占めて、解説本文
 * より目立ってしまう（「解説がリンクになっている」ように見えていた）。
 * 出典表記そのものは Public Data License 1.0 で求められるので消さない。
 */
function withLinks(line, keyPrefix) {
  const parts = line.split(URL_RE);
  return parts.map((part, i) =>
    /^https?:\/\//.test(part) ? (
      <a key={`${keyPrefix}-${i}`} href={part} target="_blank" rel="noreferrer">
        公表ページ
      </a>
    ) : (
      part
    ),
  );
}

/** 解説文を段落ごとに表示する。出典と免責は本文と分けて小さく出す。 */
export default function ExplanationText({ text }) {
  if (!text) return null;
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const body = [];
  const notes = [];
  for (const line of lines) {
    // 最初に注記が現れたら、それ以降はすべて注記として扱う。出典のURLが
    // 次の行に落ちている古い形式でも、まとめて下に送れる。
    (notes.length || isNote(line) ? notes : body).push(line);
  }

  return (
    <div className="explanation">
      {body.map((line, i) => (
        <p key={`b${i}`}>{line}</p>
      ))}
      {notes.length > 0 && (
        <div className="explanation-note">
          {notes.map((line, i) => (
            <p key={`n${i}`}>{withLinks(line, `n${i}`)}</p>
          ))}
        </div>
      )}
    </div>
  );
}
