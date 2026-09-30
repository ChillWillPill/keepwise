"""Builds www/index.html (the installable app) from src/app.html, the single source of truth.
The same src/app.html is published as the Claude artifact."""
import os, re, hashlib, json
ROOT = os.path.join(os.path.dirname(__file__), "..")
src = open(os.path.join(ROOT, "src/app.html"), encoding="utf-8").read()
version = hashlib.sha1(src.encode()).hexdigest()[:10]
head = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="See what you keep at month end: subscriptions, cheaper swaps, codes, budget and bill splitting.">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Keepwise">
<style>:root{color-scheme:light}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
</head>
<body>
"""
sw = """
<script>
// Offline support for the installed web app (skipped inside the Capacitor app, which ships its files).
if ("serviceWorker" in navigator && location.protocol === "https:" && !window.Capacitor) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
</script>
</body>
</html>
"""
os.makedirs(os.path.join(ROOT, "www"), exist_ok=True)
open(os.path.join(ROOT, "www/index.html"), "w", encoding="utf-8").write(head + src + sw)
manifest = {
  "name": "Keepwise", "short_name": "Keepwise", "description": "What you keep at month end.",
  "start_url": "./", "scope": "./", "display": "standalone", "orientation": "portrait",
  "background_color": "#f3efe6", "theme_color": "#f3efe6",
  "icons": [
    {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
json.dump(manifest, open(os.path.join(ROOT, "www/manifest.webmanifest"), "w"), indent=2)
open(os.path.join(ROOT, "www/sw.js"), "w").write(f"""// Keepwise service worker, build {version}
const CACHE = "keepwise-{version}";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];
self.addEventListener("install", e => {{ e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); }});
self.addEventListener("activate", e => {{ e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); }});
self.addEventListener("fetch", e => {{
  const req = e.request; if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (req.mode === "navigate") {{  // newest app when online, cached copy offline
    e.respondWith(fetch(req).then(r => {{ caches.open(CACHE).then(c => c.put("index.html", r.clone())); return r; }}).catch(() => caches.match("index.html")));
    return;
  }}
  if (url.origin === location.origin || url.host.endsWith("gstatic.com") || url.host.endsWith("googleapis.com")) {{
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {{ const copy = r.clone(); caches.open(CACHE).then(c => c.put(req, copy)); return r; }})));
  }}
}});
""")
print("built www/ (version", version + ")")
