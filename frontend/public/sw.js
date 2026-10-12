/* DayWell service worker.
 *
 * Caching: only the static app shell and hashed build assets. API responses (/api/*) are NEVER cached — personal data
 * stays on the server and is always fetched fresh. Navigations fall back to the cached shell when offline, where the
 * app shows its offline banner.
 *
 * Push: displays reminder notifications (tag = occ-<id>, so duplicates replace each other) and confirms display to the
 * server with a signed one-delivery receipt. A displayed notification is NOT an audible alarm: browsers decide sound,
 * and silent/do-not-disturb modes win. Actions open the app, which performs snooze/done with the user's session.
 */
const VERSION = "daywell-v1";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/badge-96.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/health/") || url.pathname.startsWith("/django-admin/")) return;

  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match("/index.html")));
    return;
  }
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/icons/") || url.pathname.startsWith("/sounds/")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(VERSION).then((cache) => cache.put(req, copy));
        }
        return res;
      })),
    );
  }
});

async function broadcast(message) {
  const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  clients.forEach((c) => c.postMessage(message));
  return clients;
}

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "DayWell", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "DayWell reminder";
  const options = {
    body: data.body || "",
    tag: data.tag || undefined,
    renotify: true,
    requireInteraction: !!data.requireInteraction,
    icon: "/icons/icon-192.png",
    badge: "/icons/badge-96.png",
    vibrate: data.vibrate ? [200, 100, 200] : undefined,
    data: { url: data.url || "/", occurrence_id: data.occurrence_id || null },
    actions: data.occurrence_id ? [
      { action: "snooze", title: `Snooze ${data.snooze_minutes || 10} min` },
      { action: "open", title: "Open" },
    ] : [],
  };
  event.waitUntil((async () => {
    await self.registration.showNotification(title, options);
    if (data.receipt) {
      // Confirm display. Failure here only means the server keeps the delivery as "accepted" (never over-claims).
      try {
        await fetch("/api/v1/push/receipt/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ receipt: data.receipt }),
          credentials: "omit",
        });
      } catch { /* offline — nothing to do */ }
    }
    await broadcast({ type: "daywell:push", occurrence_id: data.occurrence_id || null });
  })());
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const occ = event.notification.data && event.notification.data.occurrence_id;
  let target = (event.notification.data && event.notification.data.url) || "/";
  if (occ && event.action === "snooze") target = `/?alarm=${occ}&action=snooze`;
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of clients) {
      if ("focus" in client) {
        client.postMessage({ type: "daywell:notification-click", url: target });
        return client.focus();
      }
    }
    return self.clients.openWindow(target);
  })());
});

self.addEventListener("pushsubscriptionchange", (event) => {
  // The browser rotated or dropped the subscription. The app re-subscribes on its next open.
  event.waitUntil(broadcast({ type: "daywell:push-subscription-changed" }));
});
