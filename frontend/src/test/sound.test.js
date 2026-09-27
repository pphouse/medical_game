/**
 * 効果音。jsdom は HTMLMediaElement.play を実装していないので、素で呼ぶと
 * 例外になる。演習の進行を止めないこと（例外を投げないこと）が要点。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { playCorrect, playIncorrect, playVerdict } from "../lib/sound";

const played = [];

beforeEach(() => {
  played.length = 0;
  HTMLMediaElement.prototype.play = vi.fn(function play() {
    played.push(this.src);
    return Promise.resolve();
  });
});

describe("効果音", () => {
  it("正解と不正解で別の音を鳴らす", () => {
    playCorrect();
    playIncorrect();

    expect(played).toHaveLength(2);
    expect(played[0]).not.toBe(played[1]);
  });

  it("playVerdict は正誤で鳴らし分ける", () => {
    playVerdict(true);
    const correct = played[0];
    playVerdict(false);

    expect(played[1]).not.toBe(correct);
  });

  it("再生が拒否されても例外を投げない", () => {
    HTMLMediaElement.prototype.play = vi.fn(() => Promise.reject(new Error("blocked")));

    expect(() => playVerdict(true)).not.toThrow();
  });

  it("再生自体が例外になっても呼び出し側に漏らさない", () => {
    HTMLMediaElement.prototype.play = vi.fn(() => {
      throw new Error("Not implemented");
    });

    expect(() => playVerdict(false)).not.toThrow();
  });
});
