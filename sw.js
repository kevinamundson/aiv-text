// AIV service worker: caches the app shell so the reader works offline
// and the site meets the installability criteria (manifest + service
// worker + HTTPS). Network-first for pages, so content is never served
// stale; visited pages are cached as they are read, so they work offline.
const CACHE = "aiv-v1";
const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/read/reader.css",
  "/read/reader.js",
  "/read/nav-data.js",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/apple-touch-icon.png",
  "/favicon.ico"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request).then(
          (cached) =>
            cached ||
            (event.request.mode === "navigate" ? caches.match("/") : undefined)
        )
      )
  );
});
