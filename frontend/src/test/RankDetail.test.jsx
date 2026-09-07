import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RankDetail from "../components/RankDetail";

vi.mock("../lib/supabase", () => ({ supabase: null, isSupabaseConfigured: false }));
vi.mock("../api", () => ({ api: { rankDetail: vi.fn() } }));

import { api } from "../api";

function daysOf(month, counts = {}) {
  const [year, m] = month.split("-").map(Number);
  const days = new Date(year, m, 0).getDate();
  return Array.from({ length: days }, (_, i) => ({
    date: `${month}-${String(i + 1).padStart(2, "0")}`,
    count: counts[i + 1] ?? 0,
  }));
}

function detail(month, { earliest = "2026-03", latest = "2026-09", counts } = {}) {
  return {
    me: { eligible: true, rank: 3, value: 120, out_of: 40, percentile: 7.5 },
    distribution: [],
    daily: daysOf(month, counts),
    daily_range: { month, earliest_month: earliest, latest_month: latest },
    yesterday: { date: "2026-09-03", count: 5, diff: 2 },
  };
}

describe("演習状況の月送り", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.rankDetail.mockResolvedValue(detail("2026-09", { counts: { 3: 5 } }));
  });

  it("何年何月ぶんかを見出しに出す", async () => {
    render(<RankDetail scope="national" metric="solved" />);
    expect(await screen.findByText("2026年9月の演習状況")).toBeInTheDocument();
  });

  it("その月の演習数の合計を出す", async () => {
    api.rankDetail.mockResolvedValue(detail("2026-09", { counts: { 1: 10, 2: 7 } }));
    render(<RankDetail scope="national" metric="solved" />);
    expect(await screen.findByText("この月の演習数 17問")).toBeInTheDocument();
  });

  it("◀ で前の月のデータを取りに行く", async () => {
    render(<RankDetail scope="national" metric="solved" />);
    await screen.findByText("2026年9月の演習状況");
    api.rankDetail.mockResolvedValue(detail("2026-08"));

    fireEvent.click(screen.getByRole("button", { name: "前の月" }));

    await waitFor(() =>
      expect(api.rankDetail).toHaveBeenCalledWith("national", "solved", "2026-08"),
    );
    expect(await screen.findByText("2026年8月の演習状況")).toBeInTheDocument();
  });

  it("年をまたいで遡れる", async () => {
    api.rankDetail.mockResolvedValue(
      detail("2026-01", { earliest: "2025-11", latest: "2026-09" }),
    );
    render(<RankDetail scope="national" metric="solved" />);
    await screen.findByText("2026年1月の演習状況");

    fireEvent.click(screen.getByRole("button", { name: "前の月" }));

    await waitFor(() =>
      expect(api.rankDetail).toHaveBeenCalledWith("national", "solved", "2025-12"),
    );
  });

  it("記録のある最初の月では ◀ を押せない", async () => {
    api.rankDetail.mockResolvedValue(
      detail("2026-03", { earliest: "2026-03", latest: "2026-09" }),
    );
    render(<RankDetail scope="national" metric="solved" />);
    await screen.findByText("2026年3月の演習状況");

    expect(screen.getByRole("button", { name: "前の月" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "次の月" })).not.toBeDisabled();
  });

  it("今月では ▶ を押せない", async () => {
    render(<RankDetail scope="national" metric="solved" />);
    await screen.findByText("2026年9月の演習状況");

    expect(screen.getByRole("button", { name: "次の月" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "前の月" })).not.toBeDisabled();
  });
});
