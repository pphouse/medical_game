/**
 * 効果音（正解音・不正解音）。
 *
 * 出題ごとに Audio を作り直すと、iOS Safari で読み込みが間に合わず最初の
 * 数問が無音になる。音ごとに1つを使い回して、鳴らすときは頭に巻き戻す。
 */
import correctUrl from "../assets/correct.mp3";
import incorrectUrl from "../assets/incorrect.mp3";

const cache = new Map();

function element(url) {
  if (cache.has(url)) return cache.get(url);
  // jsdom（テスト）や音声を持たない環境では Audio が無い／作れない。
  let el = null;
  if (typeof Audio !== "undefined") {
    try {
      el = new Audio(url);
      el.preload = "auto";
    } catch {
      el = null;
    }
  }
  cache.set(url, el);
  return el;
}

function play(url) {
  const el = element(url);
  if (!el) return;
  try {
    el.currentTime = 0;
    const started = el.play();
    // 自動再生の制限で拒否されることがある。音が出ないだけで演習は
    // 続けられるので、失敗は黙って捨てる。
    if (started && typeof started.catch === "function") started.catch(() => {});
  } catch {
    /* 再生できない環境では鳴らさない */
  }
}

/** 正解したときの音。鳴らせない環境では何もしない。 */
export function playCorrect() {
  play(correctUrl);
}

/** 不正解だったときの音（ブザー）。鳴らせない環境では何もしない。 */
export function playIncorrect() {
  play(incorrectUrl);
}

/** 正誤に応じた音を鳴らす。 */
export function playVerdict(isCorrect) {
  if (isCorrect) playCorrect();
  else playIncorrect();
}
