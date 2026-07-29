/* 復習リマインド用 Service Worker (spec フェーズ6)。
   push 受信 → 通知表示、タップ → 復習デッキ (/review) を開く。 */

self.addEventListener("push", (event) => {
  let data = { title: "復習の時間です", body: "復習期限の問題があります。", url: "/review" };
  try {
    data = { ...data, ...event.data.json() };
  } catch {
    /* テキスト/空ペイロードは既定文言 */
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/favicon.svg",
      badge: "/favicon.svg",
      data: { url: data.url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url ?? "/review";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ("focus" in client) {
          client.focus();
          if ("navigate" in client) client.navigate(url);
          return;
        }
      }
      return clients.openWindow(url);
    })
  );
});
