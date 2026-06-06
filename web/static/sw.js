/**
 * oi-booth service worker
 * Caches the gallery and static assets so the gallery loads offline.
 */

const CACHE_NAME = "oi-booth-v1";

// Assets to pre-cache on install
const PRECACHE_URLS = [
  "/gallery",
  "/static/manifest.json",
];

// ── Install: pre-cache shell assets ─────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  // Activate immediately rather than waiting for old tabs to close
  self.skipWaiting();
});

// ── Activate: clean up old cache versions ───────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch: network-first for API/share, cache-first for gallery/static ──────
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never intercept non-GET requests or cross-origin requests
  if (event.request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;

  // API and share routes — network only, no caching
  if (url.pathname.startsWith("/share") || url.pathname.startsWith("/health")) {
    return;
  }

  // Gallery index and static assets — cache-first, fall back to network,
  // then update the cache with the fresh response
  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(event.request);
      const networkFetch = fetch(event.request)
        .then((response) => {
          // Only cache successful same-origin responses
          if (response && response.status === 200 && response.type === "basic") {
            cache.put(event.request, response.clone());
          }
          return response;
        })
        .catch(() => null);

      // Return cached copy immediately if available; background-refresh it
      if (cached) {
        // Kick off a background refresh without blocking the response
        networkFetch;
        return cached;
      }

      // No cache hit — wait for network
      const fresh = await networkFetch;
      if (fresh) return fresh;

      // Both cache and network failed — return a minimal offline page
      return new Response(
        `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>oi-booth — offline</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f0f0f; color: #e8e8e8;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; margin: 0; text-align: center; padding: 2rem;
    }
    h1 { color: #fff; margin-bottom: 0.5rem; }
    p  { color: #888; font-size: 0.9rem; }
    .brand { font-weight: 700; } .brand span { color: #f97316; }
  </style>
</head>
<body>
  <div>
    <p class="brand">oi<span>-booth</span></p>
    <h1>You're offline</h1>
    <p>Connect to the booth's network to view your photos.</p>
  </div>
</body>
</html>`,
        { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } }
      );
    })
  );
});
