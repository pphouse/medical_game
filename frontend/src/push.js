import { api } from "./api";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window;
}

/** 通知許可 → SW 登録 → Push 購読 → バックエンドへ登録。 */
export async function enablePush(vapidPublicKey) {
  if (!pushSupported()) throw new Error("このブラウザは Web Push に対応していません。");
  if (!vapidPublicKey) throw new Error("サーバーに VAPID 公開鍵が設定されていません。");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("通知が許可されませんでした。");

  const registration = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
  });
  const json = subscription.toJSON();
  await api.registerPushSubscription({ endpoint: json.endpoint, keys: json.keys });
  return subscription;
}

export async function disablePush() {
  if (!pushSupported()) return;
  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  if (subscription) {
    await api.deletePushSubscription(subscription.endpoint).catch(() => {});
    await subscription.unsubscribe();
  }
}
