import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const updateUser = vi.fn();
const signOut = vi.fn();
vi.mock("../lib/supabase", () => ({
  supabase: { auth: { updateUser: (...a) => updateUser(...a), signOut: (...a) => signOut(...a) } },
}));

const { default: Consent, hasAgreed } = await import("../legal/Consent");
const { TERMS_VERSION } = await import("../legal/documents");

describe("同意画面", () => {
  beforeEach(() => {
    updateUser.mockReset().mockResolvedValue({ error: null });
    signOut.mockReset().mockResolvedValue({});
  });

  it("今の版に同意したアカウントだけを同意済みとみなす", () => {
    expect(hasAgreed({ user: { user_metadata: { agreed_terms_version: TERMS_VERSION } } })).toBe(true);
    expect(hasAgreed({ user: { user_metadata: { agreed_terms_version: "2000-01-01" } } })).toBe(false);
    expect(hasAgreed({ user: { user_metadata: {} } })).toBe(false);
  });

  it("チェックするまで同意できず、同意すると版をアカウントに記録する", async () => {
    render(<Consent />);
    const agree = screen.getByRole("button", { name: "同意してはじめる" });
    expect(agree).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(agree);
    await waitFor(() => expect(updateUser).toHaveBeenCalledTimes(1));
    expect(updateUser.mock.calls[0][0].data.agreed_terms_version).toBe(TERMS_VERSION);
  });

  it("各文書の全文を開ける", () => {
    render(<Consent />);
    for (const title of ["医療免責事項", "利用規約", "プライバシーポリシー", "特定商取引法に基づく表記", "参考文献・出典"]) {
      fireEvent.click(screen.getByRole("button", { name: title }));
      expect(screen.getByRole("dialog", { name: title })).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "閉じる" }));
    }
  });

  it("同意しない場合はログアウトする", () => {
    render(<Consent />);
    fireEvent.click(screen.getByRole("button", { name: "同意しない（ログアウト）" }));
    expect(signOut).toHaveBeenCalled();
  });
});
