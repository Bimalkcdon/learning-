// ApexQuant — Service Worker for offline support & PWA installability
const CACHE_NAME = "apexquant-v1";
const STATIC_ASSETS = [
  "./",
  "./apexquant.html",
  "./manifest.json",
  "https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;500;600;700;800&display=swap",
  "https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&display=swap"
];

// Install — cache static assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

// Activate — clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch — serve from cache, fall back to network, cache API responses
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API requests — try network first, fall back to cache
  if (url.pathname.startsWith("/api/") || url.hostname.includes("the-odds-api.com")) {
    event.respondWith(
      fetch(request).then((response) => {
        const cloned = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, cloned));
        return response;
      }).catch(() => caches.match(request).then((cached) => cached || new Response(JSON.stringify({ success: false, offline: true }), { headers: { "Content-Type": "application/json" } })))
    );
    return;
  }

  // Static assets — cache first
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request))
  );
});
