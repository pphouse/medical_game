import "@testing-library/jest-dom/vitest";

// jsdom は HTMLMediaElement.play を実装していないため、効果音を鳴らす画面の
// テストが実行のたびに「Not implemented」を吐く。音の有無はテストの対象では
// ないので、無音のスタブを置いて出力を静かにしておく（効果音そのものの
// テストは src/test/sound.test.js で play を差し替えて確かめている）。
if (typeof HTMLMediaElement !== "undefined") {
  HTMLMediaElement.prototype.play = () => Promise.resolve();
}
