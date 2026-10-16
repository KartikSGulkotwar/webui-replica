/* WebUI Replica service worker: makes the app installable, loads it fast,
 * and shows a friendly page when offline. API calls are never cached. */
const CACHE = 'webui-v1'
const PRECACHE = ['/offline.html', '/icons/icon-192.png', '/favicon.svg', '/manifest.webmanifest']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return // always live

  // Pages: always the newest version from the network; offline page otherwise.
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/offline.html')))
    return
  }

  // Built files have content hashes in their names, so a cached copy is never stale.
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/')) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone()
              caches.open(CACHE).then((cache) => cache.put(request, copy))
            }
            return response
          }),
      ),
    )
  }
})
