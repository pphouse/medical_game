import { MEDICAL_DISCLAIMER, MHLW_EXAM_URL } from "../references";
import ReferenceList from "./ReferenceList";

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
function withLinks(line, keyPrefix, addMhlwLink = false) {
  const parts = line.split(URL_RE);
  // URL の無い国試の出典行にも、厚労省の公表ページへのリンクを添える。
  if (addMhlwLink && line.startsWith("出典：厚生労働省")) {
    return [
      line,
      "（",
      <a key={`${keyPrefix}-mhlw`} href={MHLW_EXAM_URL} target="_blank" rel="noreferrer">
        公表ページ
      </a>,
      "）",
    ];
  }
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

/** 解説文を段落ごとに表示する。
 *
 * `notes` を渡すと、選択肢ごとの解説を解説文の中に続けて並べる。選択肢の
 * 一覧を解説の下にもう一度出して、その各行に解説を添える形にすると、同じ
 * 選択肢を2回読むことになり、本文との行き来も増える。ここでは記号
 * （A〜E）だけを頼りに、解説の続きとして読めるようにする。
 *
 * 出典と免責は本文と分けて小さく出す。 */
export default function ExplanationText({ text, notes, correctKey, myKey }) {
  const lines = (text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const body = [];
  const sources = [];
  for (const line of lines) {
    // 最初に注記が現れたら、それ以降はすべて注記として扱う。出典のURLが
    // 次の行に落ちている古い形式でも、まとめて下に送れる。
    (sources.length || isNote(line) ? sources : body).push(line);
  }

  const noteRows = Object.entries(notes ?? {})
    .filter(([, note]) => note)
    .sort(([a], [b]) => (a < b ? -1 : 1));

  if (!body.length && !sources.length && !noteRows.length) return null;

  // 出典の URL が別の行にある古い形式では、そちらがリンクになる。
  const hasSourceUrl = sources.some((line) => /https?:\/\//.test(line));

  return (
    <div className="explanation">
      {body.map((line, i) => (
        <p key={`b${i}`}>{line}</p>
      ))}
      {noteRows.length > 0 && (
        <div className="explanation-choices">
          <p className="explanation-choices-heading">選択肢ごとの解説</p>
          {noteRows.map(([key, note]) => {
            const isCorrect = key === correctKey;
            const isMyMistake = key === myKey && !isCorrect;
            return (
              <p
                key={key}
                className={`explanation-choice${isCorrect ? " correct" : ""}${
                  isMyMistake ? " incorrect" : ""
                }`}
              >
                <span className="explanation-choice-key">{key}</span>
                <span>{note}</span>
              </p>
            );
          })}
        </div>
      )}
      {/* 医療情報の出典は見つけやすい所に置く（App Store Guideline 1.4.1）。
          一覧は開閉式にして、解説本文より目立たないようにする。 */}
      <div className="explanation-note">
        {sources.map((line, i) => (
          <p key={`n${i}`}>{withLinks(line, `n${i}`, !hasSourceUrl)}</p>
        ))}
        <details className="explanation-refs">
          <summary>出典・参考文献</summary>
          <ReferenceList />
        </details>
        <p>※{MEDICAL_DISCLAIMER}</p>
      </div>
    </div>
  );
}
