/* Shell: cache first. data.json: network first, cached copy when offline. */
const SHELL = "nr-shell-v1";
const FILES = ["./", "index.html", "styles.css", "app.js", "manifest.webmanifest", "icon.svg", "icon-192.png"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL && k !== "nr-data").map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.pathname.endsWith("/data.json")) {
    e.respondWith(fetch(e.request).then((r) => {
      if (r.ok) { const copy = r.clone(); caches.open("nr-data").then((c) => c.put("data.json", copy)); }
      return r;
    }).catch(() => caches.match("data.json", { ignoreSearch: true })));
    return;
  }
  if (url.origin === location.origin || url.host.endsWith("gstatic.com") || url.host.endsWith("googleapis.com")) {
    e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
      if (r.ok && url.origin !== location.origin) { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(e.request, copy)); }
      return r;
    })));
  }
});
