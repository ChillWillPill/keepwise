// KeepWise service worker, build c1f292665b
const CACHE = "keepwise-c1f292665b";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
// A nudge from KeepWise: the message carries only a title and a line of text, never anything about money.
self.addEventListener("push", e => {
  let d = {}; try { const j = e.data ? e.data.json() : {}; d = j.data || j.notification || j; } catch (x) {}
  e.waitUntil(self.registration.showNotification(d.title || "KeepWise", {body: d.body || "", icon: "icons/icon-192.png", badge: "icons/icon-192.png", tag: d.tag || "keepwise", data: {url: d.url || "./"}}));
});
self.addEventListener("notificationclick", e => {
  e.notification.close(); const to = new URL((e.notification.data && e.notification.data.url) || "./", self.location.href).href;
  e.waitUntil(clients.matchAll({type: "window", includeUncontrolled: true}).then(ws => { for (const w of ws) if ("focus" in w) { w.navigate(to).catch(() => {}); return w.focus(); } return clients.openWindow(to); }));
});
self.addEventListener("fetch", e => {
  const req = e.request; if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (req.mode === "navigate") {  // newest app when online, cached copy offline
    // Only the app page itself is saved as the offline copy, and only a good response: never an error page or another page.
    const isApp = /\/(index\.html)?$/.test(url.pathname);
    e.respondWith(fetch(req).then(r => {
      if (isApp && r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put("index.html", copy)); return r; }
      if (isApp && r.status >= 500) return caches.match("index.html").then(hit => hit || r);  // host hiccup: show the saved app
      return r;
    }).catch(() => isApp ? caches.match("index.html") : caches.match(req).then(hit => hit || caches.match("index.html"))));
    return;
  }
  if (url.origin === location.origin || url.host.endsWith("gstatic.com") || url.host.endsWith("googleapis.com")) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => { if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(req, copy)); } return r; })));
  }
});
