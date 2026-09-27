import { beforeEach, describe, expect, it, vi } from "vitest";

// vi.mock はファイル先頭に巻き上げられるので、モックが掴む関数も
// vi.hoisted で同じところまで持ち上げないと未初期化になる。
const { exchangeCodeForSession, setSession } = vi.hoisted(() => ({
  exchangeCodeForSession: vi.fn(),
  setSession: vi.fn(),
}));

vi.mock("../lib/supabase", () => ({
  supabase: { auth: { exchangeCodeForSession, setSession } },
  isSupabaseConfigured: true,
}));

import { callbackParams, completeAuthFromUrl } from "../lib/deepLink";

const CALLBACK = "jp.pphouse.medquiz://auth-callback";

describe("callbackParams", () => {
  it("reads the query string", () => {
    expect(callbackParams(`${CALLBACK}?code=abc`).get("code")).toBe("abc");
  });

  it("reads the fragment, which is where the implicit flow puts the tokens", () => {
    const params = callbackParams(`${CALLBACK}#access_token=a&refresh_token=r`);
    expect(params.get("access_token")).toBe("a");
    expect(params.get("refresh_token")).toBe("r");
  });

  it("reads both at once", () => {
    const params = callbackParams(`${CALLBACK}?code=abc#access_token=a`);
    expect(params.get("code")).toBe("abc");
    expect(params.get("access_token")).toBe("a");
  });

  it("survives a url with neither", () => {
    expect([...callbackParams(CALLBACK)]).toEqual([]);
  });
});

describe("completeAuthFromUrl", () => {
  beforeEach(() => {
    exchangeCodeForSession.mockReset().mockResolvedValue({ error: null });
    setSession.mockReset().mockResolvedValue({ error: null });
  });

  it("exchanges the PKCE code", async () => {
    await expect(completeAuthFromUrl(`${CALLBACK}?code=abc`)).resolves.toBe(true);
    expect(exchangeCodeForSession).toHaveBeenCalledWith("abc");
    expect(setSession).not.toHaveBeenCalled();
  });

  it("falls back to the implicit tokens in the fragment", async () => {
    await expect(
      completeAuthFromUrl(`${CALLBACK}#access_token=a&refresh_token=r`),
    ).resolves.toBe(true);
    expect(setSession).toHaveBeenCalledWith({ access_token: "a", refresh_token: "r" });
  });

  it("ignores a url that carries no credentials", async () => {
    await expect(completeAuthFromUrl(`${CALLBACK}`)).resolves.toBe(false);
    expect(exchangeCodeForSession).not.toHaveBeenCalled();
    expect(setSession).not.toHaveBeenCalled();
  });

  it("surfaces the error Supabase puts in the url", async () => {
    await expect(
      completeAuthFromUrl(`${CALLBACK}#error=access_denied&error_description=Link+expired`),
    ).rejects.toThrow("Link expired");
  });

  it("surfaces a failed exchange instead of pretending to be signed in", async () => {
    exchangeCodeForSession.mockResolvedValue({ error: new Error("bad code verifier") });
    await expect(completeAuthFromUrl(`${CALLBACK}?code=abc`)).rejects.toThrow(
      "bad code verifier",
    );
  });
});
