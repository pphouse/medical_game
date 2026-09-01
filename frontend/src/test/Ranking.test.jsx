import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Ranking from "../routes/Ranking";

vi.mock("../api", () => ({
  api: {
    ranking: vi.fn(),
    rankingExams: vi.fn(),
    pointsRanking: vi.fn(),
    exams: vi.fn(),
    // RankingCard 経由で常時呼ばれる（クリックしなくても詳細をインライン表示するため）。
    rankDetail: vi.fn(() => new Promise(() => {})), // 明示的に検証しないテストでは解決させない
  },
}));

import { api } from "../api";

describe("ランキング画面", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("順位・名前・値と自分の順位カードを表示する", async () => {
    api.ranking.mockResolvedValue({
      entries: [
        { rank: 1, display_name: "太郎", university: "A大学", value: 321, is_me: false },
        { rank: 2, display_name: "花子", university: null, value: 200, is_me: true },
      ],
      me: { eligible: true, rank: 2, value: 200 },
    });

    render(<Ranking />, { wrapper: MemoryRouter });

    expect(await screen.findByText("太郎")).toBeInTheDocument();
    expect(screen.getByText("A大学")).toBeInTheDocument();
    expect(screen.getByText("321問")).toBeInTheDocument();
    expect(screen.getByText("あなたの順位")).toBeInTheDocument();
    expect(screen.getByText("2位")).toBeInTheDocument();
    expect(api.ranking).toHaveBeenCalledWith({
      scope: "national",
      metric: "solved",
      period: "all",
    });
  });

  it("正答率ランキングの対象外理由（100問ゲート）を表示する", async () => {
    api.ranking.mockResolvedValue({
      entries: [],
      me: {
        eligible: false,
        reason: "正答率ランキングは100問以上解くと対象になります（あと58問）",
      },
    });

    render(<Ranking />, { wrapper: MemoryRouter });

    expect(
      await screen.findByText("正答率ランキングは100問以上解くと対象になります（あと58問）")
    ).toBeInTheDocument();
    expect(screen.getByText("まだ集計データがありません。")).toBeInTheDocument();
  });

  it("月間に切り替えると今月の期間で再取得する", async () => {
    api.ranking.mockResolvedValue({
      entries: [{ rank: 1, display_name: "太郎", university: null, value: 87, is_me: false }],
      me: null,
    });

    render(<Ranking />, { wrapper: MemoryRouter });
    await screen.findByText("太郎");

    fireEvent.click(screen.getByRole("button", { name: "月間" }));

    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    expect(api.ranking).toHaveBeenLastCalledWith({
      scope: "national",
      metric: "solved",
      period: month,
    });
  });

  it("学内に切り替えると scope=university で再取得する", async () => {
    api.ranking.mockResolvedValue({ entries: [], me: null });

    render(<Ranking />, { wrapper: MemoryRouter });
    fireEvent.click(screen.getByRole("button", { name: "学内" }));

    expect(api.ranking).toHaveBeenLastCalledWith({
      scope: "university",
      metric: "solved",
      period: "all",
    });
  });

  it("対戦タブは全国/学内のみで、通算・月間の切り替えを出さない", async () => {
    api.ranking.mockResolvedValue({ entries: [], me: null });
    api.pointsRanking.mockResolvedValue({ entries: [], me: null });

    render(<Ranking />, { wrapper: MemoryRouter });
    fireEvent.click(screen.getByRole("button", { name: "対戦" }));

    expect(await screen.findByRole("button", { name: "全国" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "学内" })).toBeInTheDocument();
    // ポイントは累計値なので期間の絞り込みは持たない。
    expect(screen.queryByRole("button", { name: "通算" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "月間" })).not.toBeInTheDocument();
  });

  it("模試タブは受験できる模試の一覧も表示する", async () => {
    api.ranking.mockResolvedValue({ entries: [], me: null });
    api.rankingExams.mockResolvedValue([]);
    api.exams.mockResolvedValue([
      {
        id: 7,
        title: "第3回 全国CBT模試",
        kind: "monthly",
        exam_type: "CBT",
        status: "open",
        question_count: 60,
        duration_minutes: 90,
        start_at: "2026-09-01T00:00:00Z",
        my_result: null,
      },
    ]);

    render(<Ranking />, { wrapper: MemoryRouter });
    fireEvent.click(screen.getByRole("button", { name: "模試" }));

    expect(await screen.findByText("第3回 全国CBT模試")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "受験を開始する" })).toBeInTheDocument();
  });

  it("模試タブは受験履歴（順位と点数）を表示する", async () => {
    api.ranking.mockResolvedValue({ entries: [], me: null });
    api.exams.mockResolvedValue([]);
    api.rankingExams.mockResolvedValue([
      {
        mock_exam_id: 1,
        title: "第1回 全国CBT模試",
        start_at: "2026-08-01T00:00:00Z",
        rank: 12,
        score: 88,
      },
      {
        mock_exam_id: 2,
        title: "第2回 全国CBT模試",
        start_at: "2026-09-05T00:00:00Z",
        rank: null,
        score: 90,
      },
    ]);

    render(<Ranking />, { wrapper: MemoryRouter });
    fireEvent.click(screen.getByRole("button", { name: "模試" }));

    expect(await screen.findByText("第1回 全国CBT模試")).toBeInTheDocument();
    expect(screen.getByText(/12位/)).toBeInTheDocument();
    // 未採点の模試は順位の代わりに「採点中」
    expect(screen.getByText(/採点中/)).toBeInTheDocument();
  });

  it("順位の詳細はクリックしなくても常に表示される", async () => {
    api.ranking.mockResolvedValue({
      entries: [],
      me: { eligible: true, rank: 3, value: 120, total: 40 },
    });
    api.rankDetail.mockResolvedValue({
      me: { eligible: true, rank: 3, out_of: 40 },
      distribution: [],
      daily: [{ date: "2026-08-31", count: 2 }],
      yesterday: { date: "2026-08-31", count: 2, diff: 1 },
    });

    render(<Ranking />, { wrapper: MemoryRouter });

    // 演習数タイルをクリックしなくても、詳細（演習数の詳細見出し）が出る。
    expect(await screen.findByText("演習数の詳細")).toBeInTheDocument();
    expect(api.rankDetail).toHaveBeenCalledWith("national", "solved");

    // 正答率タイルをクリックすると、詳細の対象がそちらに切り替わる。
    fireEvent.click(screen.getByRole("button", { name: /正答率/ }));
    expect(await screen.findByText("正答率の詳細")).toBeInTheDocument();
    expect(api.rankDetail).toHaveBeenCalledWith("national", "accuracy");
  });
});
