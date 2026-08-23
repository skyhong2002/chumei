/* 竹梅 service worker：只負責 Web Push 與 PWA 安裝性。
   刻意不做任何快取——站每 3 小時重建，離線快取只會讓人看到過期活動。 */
"use strict";

self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });

// 不攔截、不 respondWith：留給瀏覽器預設網路行為（僅為安裝性檢查存在）。
self.addEventListener("fetch", function () {});

self.addEventListener("push", function (e) {
  var data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) {}
  var title = data.title || "竹梅活動觀測站";
  var options = {
    body: data.body || "",
    icon: data.icon || "/assets/brand/logo-square-256.png",
    data: { url: data.url || "/" },
    tag: data.tag || undefined,
    lang: "zh-Hant-TW",
  };
  if (data.image) options.image = data.image;
  e.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        var u = new URL(list[i].url);
        if (u.pathname === new URL(url, self.location.origin).pathname && "focus" in list[i]) {
          return list[i].focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});

// 瀏覽器換發訂閱時自動遷移，帶舊 endpoint 讓伺服器把偏好搬過去。
self.addEventListener("pushsubscriptionchange", function (e) {
  e.waitUntil(
    self.registration.pushManager
      .subscribe(e.oldSubscription ? e.oldSubscription.options : { userVisibleOnly: true })
      .then(function (sub) {
        return fetch("/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            subscription: sub.toJSON(),
            migrate_from: e.oldSubscription ? e.oldSubscription.endpoint : null,
          }),
        });
      })
      .catch(function () {})
  );
});
