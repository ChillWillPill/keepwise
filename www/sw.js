// KeepWise service worker, build 808a6c1812
const CACHE = "keepwise-808a6c1812";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
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
