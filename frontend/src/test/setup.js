import "@testing-library/jest-dom/vitest";

// jsdom は HTMLMediaElement の play/pause を実装していないため、効果音や
// BGM を鳴らす画面のテストが実行のたびに「Not implemented」を吐く。音の
// 有無はテストの対象ではないので、無音のスタブを置いて出力を静かにして
// おく（効果音そのもののテストは src/test/sound.test.js と
// src/test/Battle.test.jsx で play を差し替えて確かめている）。
if (typeof HTMLMediaElement !== "undefined") {
  HTMLMediaElement.prototype.play = () => Promise.resolve();
  HTMLMediaElement.prototype.pause = () => {};
}
