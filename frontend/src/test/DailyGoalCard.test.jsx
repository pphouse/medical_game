import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ api: { setDailyGoal: vi.fn() } }));

import { api } from "../api";
import DailyGoalCard from "../components/DailyGoalCard";

const DAYS = [
  { date: "2026-09-19", count: 0, goal: 10, status: "none" },
  { date: "2026-09-20", count: 3, goal: 10, status: "missed" },
  { date: "2026-09-21", count: 10, goal: 10, status: "achieved" },
  { date: "2026-09-22", count: 12, goal: 10, status: "achieved" },
  { date: "2026-09-23", count: 4, goal: 10, status: "rest" },
  { date: "2026-09-24", count: 10, goal: 10, status: "achieved" },
  { date: "2026-09-25", count: 7, goal: 10, status: "today" },
];

function habit(overrides = {}) {
  return {
    date: "2026-09-25",
    goal: 10,
    count: 7,
    remaining: 3,
    achieved: false,
    streak: 3,
    rest_available: false,
    days: DAYS,
    upcoming_goal: null,
    goal_choices: [5, 10, 20, 30, 50],
    reminder: { enabled: false, hour: 20 },
    suggested_hour: null,
    reminders: [],
    ...overrides,
  };
}

describe("ホームの今日の目標", () => {
  beforeEach(() => vi.clearAllMocks());

  it("目標が無ければ、決めるところから始める", async () => {
    const onChange = vi.fn();
    const next = habit({ goal: 10, count: 0, remaining: 10 });
    api.setDailyGoal.mockResolvedValue(next);
    render(<DailyGoalCard habit={habit({ goal: null, remaining: null })} onChange={onChange} />);

    expect(screen.getByText("1日の目標を決めよう")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "10問" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(next));
    expect(api.setDailyGoal).toHaveBeenCalledWith(10);
  });

  it("残りの問題数・連続日数・1週間の記録を出す", () => {
    render(<DailyGoalCard habit={habit()} onChange={vi.fn()} />);
    expect(screen.getByText("あと3問")).toBeInTheDocument();
    expect(screen.getByText("今日 7/10問")).toBeInTheDocument();
    expect(screen.getByLabelText("3日連続")).toBeInTheDocument();
    expect(screen.getByLabelText("9月23日: お休み")).toHaveTextContent("休");
    expect(screen.getByLabelText("9月22日: 達成")).toHaveTextContent("✓");
    expect(screen.getByLabelText("9月20日: 未達")).toBeInTheDocument();
    expect(screen.getByLabelText("9月25日: 今日")).toBeInTheDocument();
  });

  it("達成した日と、明日からの目標を出す", () => {
    render(
      <DailyGoalCard
        habit={habit({
          count: 10,
          remaining: 0,
          achieved: true,
          streak: 4,
          upcoming_goal: { questions_per_day: 20, effective_from: "2026-09-26" },
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("今日の目標を達成！")).toBeInTheDocument();
    expect(screen.getByText("今日 10/10問・明日から20問")).toBeInTheDocument();
  });

  it("目標を変える画面から、変えずに戻れる", () => {
    render(<DailyGoalCard habit={habit()} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "目標を変える（今は10問）" }));
    expect(screen.getByText("1日の目標を変える")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "10問" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "変えずに戻る" }));
    expect(screen.getByText("あと3問")).toBeInTheDocument();
    expect(api.setDailyGoal).not.toHaveBeenCalled();
  });

  it("保存に失敗したら理由を出す", async () => {
    api.setDailyGoal.mockRejectedValue(new Error("通信に失敗しました"));
    render(<DailyGoalCard habit={habit({ goal: null })} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "5問" }));
    expect(await screen.findByText("通信に失敗しました")).toBeInTheDocument();
  });
});
