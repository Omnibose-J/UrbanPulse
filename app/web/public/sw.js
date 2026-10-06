// Service worker for the weekend reminder (design spec 5.15). It only shows pushes and opens their link; nothing is
// cached and no request is intercepted.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  if (!event.data) return;
  let payload;
  try {
    payload = event.data.json();
  } catch {
    return;
  }
  if (!payload || typeof payload.title !== "string" || typeof payload.body !== "string") return;
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icon.svg",
      data: { url: typeof payload.url === "string" ? payload.url : "/" },
      tag: "urbanpulse-weekend",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data && event.notification.data.url ? event.notification.data.url : "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((client) => client.url === url && "focus" in client);
      if (open) return open.focus();
      return self.clients.openWindow(url);
    }),
  );
});
