import { describe, expect, it } from "vitest";
import { authErrorMessage } from "../lib/authErrors";

describe("authErrorMessage", () => {
  it("error.code があればそれで訳す", () => {
    expect(authErrorMessage({ code: "email_not_confirmed", message: "Email not confirmed" })).toMatch(
      "確認メール",
    );
    expect(authErrorMessage({ code: "invalid_credentials", message: "Invalid login credentials" })).toBe(
      "メールアドレスまたはパスワードが正しくありません。",
    );
  });

  it("code が無くても文言で拾う（メールのリンクから戻った error_description など）", () => {
    expect(authErrorMessage("Email link is invalid or has expired")).toMatch("有効期限");
    expect(authErrorMessage(new TypeError("Load failed"))).toMatch("通信に失敗");
    expect(authErrorMessage({ message: "Too many requests", status: 429 })).toMatch("しばらく時間");
  });

  it("知らないエラーは元の文言のまま", () => {
    expect(authErrorMessage(new Error("表示名は50文字以内です"))).toBe("表示名は50文字以内です");
  });
});
