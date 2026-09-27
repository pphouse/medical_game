/**
 * 効果音（正解音・不正解音）と、対戦中のBGM。
 *
 * 出題ごとに Audio を作り直すと、iOS Safari で読み込みが間に合わず最初の
 * 数問が無音になる。音ごとに1つを使い回して、鳴らすときは頭に巻き戻す。
 */
import battleBgmUrl from "../assets/battle-bgm.mp3";
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

// 対戦中のBGM。効果音より控えめな音量にして、正誤の音がかき消されないようにする。
const BGM_VOLUME = 0.3;
let waitingForGesture = null;

/** 対戦中のBGMを繰り返し再生する。すでに鳴っていれば何もしない。 */
export function startBattleBgm() {
  const el = element(battleBgmUrl);
  if (!el) return;
  el.loop = true;
  el.volume = BGM_VOLUME;
  try {
    const started = el.play();
    if (started && typeof started.catch === "function") {
      started.catch(() => waitForGesture(el));
    }
  } catch {
    waitForGesture(el);
  }
}

/** 対戦中のBGMを止めて、頭に戻す。 */
export function stopBattleBgm() {
  cancelGestureWait();
  const el = cache.get(battleBgmUrl);
  if (!el) return;
  try {
    el.pause();
    el.currentTime = 0;
  } catch {
    /* 止められない環境では何もしない */
  }
}

/** 自動再生を断られたとき、次に画面へ触れた時点で鳴らし直す。
 *
 * ブラウザは操作のない音の再生を止める。対戦は部屋に入る操作を経ているので
 * 普通は鳴るが、端末や設定によっては断られる。そのときのための保険。 */
function waitForGesture(el) {
  if (waitingForGesture || typeof window === "undefined") return;
  waitingForGesture = () => {
    cancelGestureWait();
    try {
      const started = el.play();
      if (started && typeof started.catch === "function") started.catch(() => {});
    } catch {
      /* それでも鳴らないなら諦める */
    }
  };
  window.addEventListener("pointerdown", waitingForGesture, { once: true });
}

function cancelGestureWait() {
  if (!waitingForGesture || typeof window === "undefined") return;
  window.removeEventListener("pointerdown", waitingForGesture);
  waitingForGesture = null;
}
