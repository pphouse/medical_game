import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { signOut } = vi.hoisted(() => ({ signOut: vi.fn() }));

vi.mock("../api", () => ({
  api: {
    deleteAccount: vi.fn(),
    universities: vi.fn(),
    updateMe: vi.fn(),
    summary: vi.fn(),
    pointsRanking: vi.fn(),
    rankingExams: vi.fn(),
  },
}));
vi.mock("../lib/supabase", () => ({
  supabase: { auth: { signOut } },
  isSupabaseConfigured: true,
}));

const navigate = vi.fn();
vi.mock("react-router-dom", async () => ({
  ...(await vi.importActual("react-router-dom")),
  useNavigate: () => navigate,
}));

const profile = {
  id: "u1",
  display_name: "テスト太郎",
  role: "student",
  student_verified: false,
  points: 0,
  grade: null,
  university: null,
  exam_preference: "",
};
vi.mock("../context/ProfileContext", () => ({
  useProfile: () => ({ profile, setProfile: vi.fn(), refresh: vi.fn() }),
}));

import { api } from "../api";
import MyPage from "../components/MyPage";

function renderMyPage() {
  return render(
    <MemoryRouter>
      <MyPage />
    </MemoryRouter>,
  );
}

async function openDangerZone() {
  renderMyPage();
  fireEvent.click(await screen.findByRole("button", { name: "アカウントを削除" }));
}

describe("アカウント削除", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.universities.mockResolvedValue([]);
    api.summary.mockResolvedValue({
      university_rank: { rank: 3, out_of: 40 },
      national_rank: { rank: 120, out_of: 5000 },
    });
    api.pointsRanking.mockResolvedValue({ entries: [], me: null });
    api.rankingExams.mockResolvedValue([]);
    api.deleteAccount.mockResolvedValue(null);
  });

  it("何が消えて何が残るかを先に見せる", async () => {
    await openDangerZone();

    expect(screen.getByText(/この操作は取り消せません/)).toBeInTheDocument();
    expect(screen.getByText(/作成者の表示を外したうえで残ります/)).toBeInTheDocument();
  });

  it("「削除」と入力するまで実行できない", async () => {
    await openDangerZone();
    const button = screen.getByRole("button", { name: "完全に削除する" });

    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/「削除」と入力/), {
      target: { value: "けす" },
    });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/「削除」と入力/), {
      target: { value: "削除" },
    });
    expect(button).toBeEnabled();
  });

  it("削除したらセッションも捨ててログイン画面へ送る", async () => {
    await openDangerZone();
    fireEvent.change(screen.getByLabelText(/「削除」と入力/), {
      target: { value: "削除" },
    });
    fireEvent.click(screen.getByRole("button", { name: "完全に削除する" }));

    await waitFor(() => expect(api.deleteAccount).toHaveBeenCalled());
    await waitFor(() => expect(signOut).toHaveBeenCalled());
    expect(navigate).toHaveBeenCalledWith("/auth?deleted=1", { replace: true });
  });

  it("失敗したら理由を出して、消えたことにしない", async () => {
    api.deleteAccount.mockRejectedValue(new Error("いま削除できません"));
    await openDangerZone();
    fireEvent.change(screen.getByLabelText(/「削除」と入力/), {
      target: { value: "削除" },
    });
    fireEvent.click(screen.getByRole("button", { name: "完全に削除する" }));

    expect(await screen.findByText("いま削除できません")).toBeInTheDocument();
    expect(signOut).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });
});
