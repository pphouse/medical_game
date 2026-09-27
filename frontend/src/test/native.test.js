import { describe, expect, it } from "vitest";

// モックせずに本物を読み込む。Web のバンドルに Capacitor を混ぜても
// 「ブラウザなのにネイティブ扱い」にならないことを確かめるため。
import { authRedirectUrl, isLiveReload, isNative, platform } from "../native";

describe("実行環境の判定", () => {
  it("ブラウザではネイティブ扱いにしない", () => {
    expect(isNative).toBe(false);
    expect(platform).toBe("web");
    expect(isLiveReload).toBe(false);
  });

  it("ブラウザではメールの戻り先が自分のオリジンになる", () => {
    expect(authRedirectUrl()).toBe(window.location.origin);
  });
});
