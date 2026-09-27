import { afterEach, describe, expect, it, vi } from "vitest";

// api.js は起動時に一度だけ宛先を決めるので、宛先ごとにモジュールを読み直す。
vi.mock("../lib/supabase", () => ({ supabase: null, isSupabaseConfigured: false }));

async function loadApi({ isNative, baseUrl }) {
  vi.resetModules();
  vi.doMock("../native", () => ({
    isNative,
    platform: isNative ? "ios" : "web",
    nativeStorage: {},
    authRedirectUrl: () => "https://example.test",
    DEEP_LINK_SCHEME: "jp.pphouse.medquiz",
    AUTH_CALLBACK_URL: "jp.pphouse.medquiz://auth-callback",
  }));
  vi.stubEnv("VITE_API_BASE_URL", baseUrl);
  return import("../api");
}

afterEach(() => {
  vi.doUnmock("../native");
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("API の宛先", () => {
  it("ブラウザでは相対パスの /api を使う（開発プロキシ・同一ドメイン配信）", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await loadApi({ isNative: false, baseUrl: "" });
    await api.me();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/me/");
  });

  it("iOS アプリで宛先が未設定なら、黙って失敗せず設定不足だと言う", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await loadApi({ isNative: true, baseUrl: "" });

    // capacitor://localhost/api を叩きに行くと「なぜか通信できない」で終わる。
    await expect(api.me()).rejects.toThrow(/VITE_API_BASE_URL/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("iOS アプリでは設定された絶対 URL を使う", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await loadApi({ isNative: true, baseUrl: "https://api.example.test/api/" });
    await api.me();

    expect(fetchMock.mock.calls[0][0]).toBe("https://api.example.test/api/auth/me/");
  });
});
