import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Ranking from "../routes/Ranking";

vi.mock("../api", () => ({
  api: {
    ranking: vi.fn(),
    rankingExams: vi.fn(),
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

    render(<Ranking />);

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

    render(<Ranking />);

    expect(
      await screen.findByText("正答率ランキングは100問以上解くと対象になります（あと58問）")
    ).toBeInTheDocument();
    expect(screen.getByText("まだ集計データがありません。")).toBeInTheDocument();
  });

  it("正答率メトリクスに切り替えると % 表示で再取得する", async () => {
    api.ranking.mockResolvedValue({
      entries: [{ rank: 1, display_name: "太郎", university: null, value: 87, is_me: false }],
      me: null,
    });

    render(<Ranking />);
    await screen.findByText("太郎");

    fireEvent.click(screen.getByText("正答率"));

    expect(await screen.findByText("87%")).toBeInTheDocument();
    expect(api.ranking).toHaveBeenLastCalledWith({
      scope: "national",
      metric: "accuracy",
      period: "all",
    });
  });

  it("模試タブは受験履歴（順位と点数）を表示する", async () => {
    api.ranking.mockResolvedValue({ entries: [], me: null });
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

    render(<Ranking />);
    fireEvent.click(screen.getByText("模試"));

    expect(await screen.findByText("第1回 全国CBT模試")).toBeInTheDocument();
    expect(screen.getByText(/12位/)).toBeInTheDocument();
    // 未採点の模試は順位の代わりに「採点中」
    expect(screen.getByText(/採点中/)).toBeInTheDocument();
  });
});
