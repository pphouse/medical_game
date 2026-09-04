import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReviewDeck from "../components/ReviewDeck";
import { ProfileProvider } from "../context/ProfileContext";

vi.mock("../lib/supabase", () => ({ supabase: null, isSupabaseConfigured: false }));
vi.mock("../api", () => ({
  api: {
    bootstrap: vi.fn(() => Promise.resolve({ resolved_exam_type: "CBT" })),
    reviewFilter: vi.fn(),
    rankingExams: vi.fn(() => Promise.resolve([])),
  },
}));

import { api } from "../api";

function renderDeck() {
  return render(
    <MemoryRouter>
      <ProfileProvider>
        <ReviewDeck />
      </ProfileProvider>
    </MemoryRouter>,
  );
}

function filterResult({ categories = ["循環器"], count = 3 } = {}) {
  return {
    count,
    truncated: false,
    available_categories: categories,
    results: Array.from({ length: count }, (_, i) => ({ id: i + 1, category: categories[0] })),
  };
}

describe("総合演習", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.bootstrap.mockResolvedValue({ resolved_exam_type: "CBT" });
    api.rankingExams.mockResolvedValue([]);
    api.reviewFilter.mockResolvedValue(filterResult());
  });

  it("CBT・医師国家試験・模試復習・対戦復習の4つの欄を出す", async () => {
    renderDeck();

    expect(await screen.findByText("総合演習")).toBeInTheDocument();
    for (const label of ["CBT", "医師国家試験", "模試復習", "対戦復習"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("CBTタブは試験種別をCBTに固定し、試験種別の選択欄は出さない", async () => {
    renderDeck();

    await waitFor(() =>
      expect(api.reviewFilter).toHaveBeenCalledWith(
        expect.objectContaining({ examType: "CBT", source: null }),
      ),
    );
    expect(screen.queryByText("試験種別")).not.toBeInTheDocument();
  });

  it("模試復習は source=mock で絞り、科目・評価・演習回数を選べる", async () => {
    renderDeck();
    await screen.findByText("科目");

    fireEvent.click(screen.getByRole("button", { name: "模試復習" }));

    await waitFor(() =>
      expect(api.reviewFilter).toHaveBeenCalledWith(
        expect.objectContaining({ source: "mock" }),
      ),
    );
    expect(await screen.findByText("科目")).toBeInTheDocument();
    expect(screen.getByText("評価")).toBeInTheDocument();
    expect(screen.getByText("演習回数")).toBeInTheDocument();
    // 模試・対戦の復習は試験種別もまたぐので選べるようにする
    expect(screen.getByText("試験種別")).toBeInTheDocument();
  });

  it("対戦復習は source=battle で絞る", async () => {
    renderDeck();
    await screen.findByText("科目");

    fireEvent.click(screen.getByRole("button", { name: "対戦復習" }));

    await waitFor(() =>
      expect(api.reviewFilter).toHaveBeenCalledWith(
        expect.objectContaining({ source: "battle" }),
      ),
    );
  });

  it("まだ模試で解いた問題が無いときは、その旨を案内する", async () => {
    renderDeck();
    await screen.findByText("科目");
    api.reviewFilter.mockResolvedValue(filterResult({ categories: [], count: 0 }));

    fireEvent.click(screen.getByRole("button", { name: "模試復習" }));

    expect(
      await screen.findByText(/まだ模試で解いた問題がありません/),
    ).toBeInTheDocument();
  });

  it("選んだ科目の問題数を演習開始ボタンに出す", async () => {
    api.reviewFilter.mockResolvedValue(filterResult({ count: 12 }));
    renderDeck();

    expect(
      await screen.findByRole("button", { name: "演習を始める（12問）" }),
    ).toBeInTheDocument();
  });
});
