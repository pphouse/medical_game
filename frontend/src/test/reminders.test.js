import { beforeEach, describe, expect, it, vi } from "vitest";

// iOS アプリとして動かす。端末に予約する通知は、サーバの予定で丸ごと置き換わる。
vi.mock("../native", () => ({ isNative: true }));
vi.mock("../lib/supabase", () => ({ supabase: null }));
vi.mock("../api", () => ({
  api: { habitToday: vi.fn(), updateNotificationPrefs: vi.fn() },
}));
const LocalNotifications = vi.hoisted(() => ({
  getPending: vi.fn(),
  cancel: vi.fn(),
  checkPermissions: vi.fn(),
  requestPermissions: vi.fn(),
  schedule: vi.fn(),
}));
vi.mock("@capacitor/local-notifications", () => ({ LocalNotifications }));

import { api } from "../api";
import { enableReminders, sendTestReminder, syncReminders } from "../reminders";

const PLAN = {
  reminders: [
    {
      id: 202609252,
      at: "2026-09-25T21:00:00+09:00",
      kind: "streak",
      title: "連続3日",
      body: "今日の目標まであと2問です。",
      url: "/",
    },
    {
      id: 202609261,
      at: "2026-09-26T20:00:00+09:00",
      kind: "daily",
      title: "今日の10問",
      body: "今日の10問から始めましょう。",
      url: "/review",
    },
  ],
};

describe("iOS の通知の予約", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    LocalNotifications.getPending.mockResolvedValue({
      notifications: [{ id: 202609251 }, { id: 202609252 }],
    });
    LocalNotifications.checkPermissions.mockResolvedValue({ display: "granted" });
  });

  it("予約済みの通知を消してから、サーバの予定を予約し直す", async () => {
    await syncReminders(PLAN);
    expect(LocalNotifications.cancel).toHaveBeenCalledWith({
      notifications: [{ id: 202609251 }, { id: 202609252 }],
    });
    const [{ notifications }] = LocalNotifications.schedule.mock.calls[0];
    expect(notifications).toHaveLength(2);
    expect(notifications[1]).toMatchObject({
      id: 202609261,
      title: "今日の10問",
      body: "今日の10問から始めましょう。",
      extra: { url: "/review" },
    });
    expect(notifications[1].schedule.at.toISOString()).toBe("2026-09-26T11:00:00.000Z");
  });

  it("通知を止めたら（予定が空なら）消すだけ", async () => {
    await syncReminders({ reminders: [] });
    expect(LocalNotifications.cancel).toHaveBeenCalled();
    expect(LocalNotifications.schedule).not.toHaveBeenCalled();
  });

  it("通知が許可されていなければ予約しない", async () => {
    LocalNotifications.checkPermissions.mockResolvedValue({ display: "denied" });
    await syncReminders(PLAN);
    expect(LocalNotifications.schedule).not.toHaveBeenCalled();
  });

  it("予定を渡さなければサーバから取ってくる", async () => {
    api.habitToday.mockResolvedValue(PLAN);
    await syncReminders();
    expect(api.habitToday).toHaveBeenCalled();
    expect(LocalNotifications.schedule).toHaveBeenCalled();
  });

  it("予約に失敗しても例外を投げない（学習の邪魔をしない）", async () => {
    LocalNotifications.schedule.mockRejectedValueOnce(new Error("boom"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await expect(syncReminders(PLAN)).resolves.toBeUndefined();
    warn.mockRestore();
  });

  it("「通知を試す」は数秒後に1通だけ予約し、予約の作り直しでは消さない", async () => {
    const before = Date.now();
    expect(await sendTestReminder()).toEqual({ ok: true, delayed: true });
    const [{ notifications }] = LocalNotifications.schedule.mock.calls[0];
    expect(notifications).toHaveLength(1);
    expect(notifications[0]).toMatchObject({
      id: 1,
      title: "通知のテスト",
      extra: { url: "/mypage" },
    });
    const delay = notifications[0].schedule.at.getTime() - before;
    expect(delay).toBeGreaterThanOrEqual(4000);
    expect(delay).toBeLessThan(10000);

    LocalNotifications.getPending.mockResolvedValue({
      notifications: [{ id: 1 }, { id: 202609261 }],
    });
    await syncReminders(PLAN);
    expect(LocalNotifications.cancel).toHaveBeenCalledWith({ notifications: [{ id: 202609261 }] });
  });

  it("通知が許可されていなければ「通知を試す」は理由を返す", async () => {
    LocalNotifications.checkPermissions.mockResolvedValue({ display: "denied" });
    expect(await sendTestReminder()).toEqual({ ok: false, reason: "denied" });
    expect(LocalNotifications.schedule).not.toHaveBeenCalled();
  });

  it("オンにするときは先に許可を求め、断られたら設定を変えない", async () => {
    LocalNotifications.requestPermissions.mockResolvedValue({ display: "denied" });
    expect(await enableReminders(20)).toEqual({ ok: false, reason: "denied" });
    expect(api.updateNotificationPrefs).not.toHaveBeenCalled();

    LocalNotifications.requestPermissions.mockResolvedValue({ display: "granted" });
    api.habitToday.mockResolvedValue(PLAN);
    const result = await enableReminders(7);
    expect(result).toEqual({ ok: true, habit: PLAN });
    expect(api.updateNotificationPrefs).toHaveBeenCalledWith({ enabled: true, preferred_hour: 7 });
    expect(LocalNotifications.schedule).toHaveBeenCalled();
  });
});
