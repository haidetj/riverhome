// Homekeep service worker — caches the app shell only.
// The ledger lives in IndexedDB, not here, and the one outbound call the app
// makes (a photo to Anthropic, when a key is set) is never cached: it is a
// request about a specific moment and a stale answer would be worse than none.
const SHELL = "homekeep-shell-v1";
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
  // Only serve the local app shell from cache; let every network call pass through.
  if (url.origin !== self.location.origin) return;
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request)));
});
