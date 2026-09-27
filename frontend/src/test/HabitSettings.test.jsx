import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ api: { habitToday: vi.fn(), setDailyGoal: vi.fn() } }));
vi.mock("../reminders", () => ({
  REMINDER_ERRORS: { denied: "通知が許可されていません。", unsupported: "対応していません。" },
  disableReminders: vi.fn(),
  enableReminders: vi.fn(),
  remindersSupported: vi.fn(() => true),
  sendTestReminder: vi.fn(),
  setReminderHour: vi.fn(),
  syncReminders: vi.fn(),
}));

import { api } from "../api";
import HabitSettings from "../components/HabitSettings";
import {
  disableReminders,
  enableReminders,
  remindersSupported,
  sendTestReminder,
  setReminderHour,
} from "../reminders";

function habit(overrides = {}) {
  return {
    date: "2026-09-25",
    goal: 10,
    count: 0,
    remaining: 10,
    achieved: false,
    streak: 0,
    rest_available: true,
    days: [],
    upcoming_goal: null,
    goal_choices: [5, 10, 20, 30, 50],
    reminder: { enabled: false, hour: 20 },
    suggested_hour: 7,
    reminders: [],
    ...overrides,
  };
}

const reminderSwitch = () => screen.getByRole("switch", { name: "リマインド" });

describe("マイページの目標とリマインド", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    remindersSupported.mockReturnValue(true);
  });

  it("通知をオンにすると許可を求め、いつもの時刻を勧める", async () => {
    api.habitToday.mockResolvedValue(habit());
    enableReminders.mockResolvedValue({
      ok: true,
      habit: habit({ reminder: { enabled: true, hour: 20 } }),
    });
    render(<HabitSettings />);

    fireEvent.click(await screen.findByRole("switch", { name: "リマインド" }));
    await waitFor(() => expect(reminderSwitch()).toHaveAttribute("aria-checked", "true"));
    expect(enableReminders).toHaveBeenCalledWith(20);
    expect(screen.getByText(/いつも7時ごろに解き始めています/)).toBeInTheDocument();

    setReminderHour.mockResolvedValue(habit({ reminder: { enabled: true, hour: 7 } }));
    fireEvent.click(screen.getByRole("button", { name: "7時にする" }));
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("7"));
    expect(setReminderHour).toHaveBeenCalledWith(7);
  });

  it("許可されなかったら理由を出し、オフのまま", async () => {
    api.habitToday.mockResolvedValue(habit());
    enableReminders.mockResolvedValue({ ok: false, reason: "denied" });
    render(<HabitSettings />);

    fireEvent.click(await screen.findByRole("switch", { name: "リマインド" }));
    expect(await screen.findByText("通知が許可されていません。")).toBeInTheDocument();
    expect(reminderSwitch()).toHaveAttribute("aria-checked", "false");
  });

  it("オフにできる", async () => {
    api.habitToday.mockResolvedValue(habit({ reminder: { enabled: true, hour: 20 } }));
    disableReminders.mockResolvedValue(habit());
    render(<HabitSettings />);

    fireEvent.click(await screen.findByRole("switch", { name: "リマインド" }));
    await waitFor(() => expect(reminderSwitch()).toHaveAttribute("aria-checked", "false"));
    expect(disableReminders).toHaveBeenCalled();
  });

  it("通知がオンなら、届くか試せる", async () => {
    api.habitToday.mockResolvedValue(habit({ reminder: { enabled: true, hour: 20 } }));
    sendTestReminder.mockResolvedValue({ ok: true, delayed: true });
    render(<HabitSettings />);

    fireEvent.click(await screen.findByRole("button", { name: "通知を試す" }));
    expect(
      await screen.findByText("5秒後に届きます。ホーム画面に戻って待ってください。"),
    ).toBeInTheDocument();

    sendTestReminder.mockResolvedValue({ ok: false, reason: "denied" });
    fireEvent.click(screen.getByRole("button", { name: "通知を試す" }));
    expect(await screen.findByText("通知が許可されていません。")).toBeInTheDocument();
  });

  it("通知がオフのうちは「通知を試す」を出さない", async () => {
    api.habitToday.mockResolvedValue(habit());
    render(<HabitSettings />);
    await screen.findByRole("switch", { name: "リマインド" });
    expect(screen.queryByRole("button", { name: "通知を試す" })).not.toBeInTheDocument();
  });

  it("目標が無いうちは通知をオンにできない", async () => {
    api.habitToday.mockResolvedValue(habit({ goal: null }));
    render(<HabitSettings />);
    expect(await screen.findByRole("switch", { name: "リマインド" })).toBeDisabled();
    expect(screen.getByText("先に1日の目標を決めてください。")).toBeInTheDocument();
  });

  it("通知に対応していない環境では、理由を出してオンにさせない", async () => {
    remindersSupported.mockReturnValue(false);
    api.habitToday.mockResolvedValue(habit());
    render(<HabitSettings />);
    expect(await screen.findByRole("switch", { name: "リマインド" })).toBeDisabled();
    expect(screen.getByText("対応していません。")).toBeInTheDocument();
  });

  it("サーバが目標を返せないときは、項目ごと出さない", async () => {
    api.habitToday.mockRejectedValue(new Error("APIエラー (500)"));
    const { container } = render(<HabitSettings />);
    await waitFor(() => expect(api.habitToday).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
