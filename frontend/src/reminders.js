import { api } from "./api";
import { supabase } from "./lib/supabase";
import { isNative } from "./native";

/**
 * 学習リマインド。
 *
 * - iOS アプリ: 端末内に予約する（ローカル通知）。サーバが返す予定
 *   （/habits/today/ の reminders）で予約を丸ごと置き換えるだけなので、文面と
 *   「いつ送るか・いつやめるか」の決まりはサーバ（habits/progress.py）にある。
 * - ブラウザ: Web Push を購読し、サーバが毎時送る。iPhone の Safari は
 *   ホーム画面に追加したときしか Web Push を受け取れない。
 *
 * 設定（オン/オフ・時刻）はサーバの通知設定に1つだけ持つ。
 */

const SERVICE_WORKER_URL = "/sw.js";

export function remindersSupported() {
  if (isNative) return true;
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** 失敗したときに画面に出す文。 */
export const REMINDER_ERRORS = {
  denied: isNative
    ? "通知が許可されていません。設定アプリの「通知」から、このアプリの通知を許可してください。"
    : "通知が許可されていません。ブラウザの設定で、このサイトの通知を許可してください。",
  unsupported:
    "このブラウザは通知に対応していません。iPhone の Safari では、ホーム画面に追加すると受け取れます。",
  unavailable: "通知の準備ができていません。しばらくしてからもう一度お試しください。",
};

async function localNotifications() {
  const { LocalNotifications } = await import("@capacitor/local-notifications");
  return LocalNotifications;
}

/** iOS: 端末に予約してある通知を、サーバの予定で置き換える。ブラウザでは何もしない。 */
export async function syncReminders(habit) {
  if (!isNative) return;
  try {
    const LocalNotifications = await localNotifications();
    const plan = habit ?? (await api.habitToday());
    const { notifications: pending } = await LocalNotifications.getPending();
    if (pending.length) {
      await LocalNotifications.cancel({ notifications: pending.map((n) => ({ id: n.id })) });
    }
    const { display } = await LocalNotifications.checkPermissions();
    if (display !== "granted" || !plan?.reminders?.length) return;
    await LocalNotifications.schedule({
      notifications: plan.reminders.map((r) => ({
        id: r.id,
        title: r.title,
        body: r.body,
        schedule: { at: new Date(r.at), allowWhileIdle: true },
        extra: { url: r.url },
      })),
    });
  } catch (err) {
    // 予約に失敗しても学習の邪魔はしない。次にホームを開いたときに作り直す。
    console.warn("reminders: sync failed", err);
  }
}

/** ログインしているときだけ予約を作り直す（アプリが前面に戻ったとき用）。 */
export async function syncRemindersIfSignedIn() {
  if (!isNative || !supabase) return;
  const { data } = await supabase.auth.getSession();
  if (data.session) await syncReminders();
}

function urlBase64ToUint8Array(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function subscribeWebPush() {
  if (!remindersSupported()) return { ok: false, reason: "unsupported" };
  const prefs = await api.notificationPrefs();
  if (!prefs.vapid_public_key) return { ok: false, reason: "unavailable" };
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return { ok: false, reason: "denied" };
  const registration = await navigator.serviceWorker.register(SERVICE_WORKER_URL);
  await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(prefs.vapid_public_key),
    }));
  const { endpoint, keys } = subscription.toJSON();
  await api.registerPush({ endpoint, keys });
  return { ok: true };
}

async function unsubscribeWebPush() {
  if (!("serviceWorker" in navigator)) return;
  const registration = await navigator.serviceWorker.getRegistration(SERVICE_WORKER_URL);
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return;
  await api.unregisterPush(subscription.endpoint).catch(() => {});
  await subscription.unsubscribe().catch(() => {});
}

/** 通知をオンにする。許可を求めてから設定を保存し、新しい今日の状態を返す。 */
export async function enableReminders(hour) {
  if (isNative) {
    const LocalNotifications = await localNotifications();
    const { display } = await LocalNotifications.requestPermissions();
    if (display !== "granted") return { ok: false, reason: "denied" };
  } else {
    const subscribed = await subscribeWebPush();
    if (!subscribed.ok) return subscribed;
  }
  await api.updateNotificationPrefs({ enabled: true, preferred_hour: hour });
  const habit = await api.habitToday();
  await syncReminders(habit);
  return { ok: true, habit };
}

/** 通知をオフにする（このブラウザの購読も外す）。新しい今日の状態を返す。 */
export async function disableReminders() {
  await api.updateNotificationPrefs({ enabled: false });
  if (!isNative) await unsubscribeWebPush();
  const habit = await api.habitToday();
  await syncReminders(habit);
  return habit;
}

/** 通知の時刻を変える。新しい今日の状態を返す。 */
export async function setReminderHour(hour) {
  await api.updateNotificationPrefs({ preferred_hour: hour });
  const habit = await api.habitToday();
  await syncReminders(habit);
  return habit;
}
