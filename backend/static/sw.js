const CACHE_NAME = "study-companion-shell-v1";
const SHELL_ASSETS = [
  "/",
  "/static/styles.css",
  "/static/app.js",
  "/static/resources.js",
  "/static/toolbox.js",
  "/static/assessment.js",
  "/static/manifest.webmanifest",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => undefined)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const isStatic = url.pathname.startsWith("/static/");
  const isApi = url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/") ||
    url.pathname.startsWith("/documents/") || url.pathname.startsWith("/tasks/") ||
    url.pathname.startsWith("/chat/") || url.pathname.startsWith("/progress/") ||
    url.pathname.startsWith("/resources/") || url.pathname.startsWith("/toolbox/") ||
    url.pathname.startsWith("/assessment/") || url.pathname.startsWith("/health");

  if (isApi) {
    // Network first; fall back to cache only if available.
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => undefined);
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  if (isStatic) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((response) => {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => undefined);
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
    return;
  }

  // Navigation / shell: network first, cache fallback.
  event.respondWith(
    fetch(request).catch(() => caches.match("/"))
  );
});