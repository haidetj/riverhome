// RiverHome service worker — caches the app shell only.
// Live data (USGS, Open-Meteo, iNaturalist, Anthropic) is NEVER cached:
// conditions must always be fresh, so those requests bypass the cache entirely.
const SHELL = "riverhome-shell-v3";
const ASSETS = ["./index.html", "./manifest.json", "./icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Only serve the local app shell from cache; let every network/API call pass through.
  const isShell = url.origin === self.location.origin;
  if (!isShell) return;
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
