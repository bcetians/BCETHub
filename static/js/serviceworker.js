const CACHE_NAME = 'bcet-portal-v5';
const STATIC_ASSETS = [
  '/',
  '/routine',
  '/mess-menu',
  '/study',
  '/notes',
  '/pyq',
  '/assignments',
  '/community',
  '/about',
  '/static/css/main-style.css',
  '/static/js/offline-routine-sync.js',
  '/static/pwaj/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return Promise.all(
        STATIC_ASSETS.map(url => {
          return cache.add(url).catch(err => console.log('Asset cache warning:', url, err));
        })
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  if (req.method !== 'GET') return;

  // Handle HTML Page Navigation Requests (Network First, Cache Fallback)
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const copy = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return networkResponse;
        })
        .catch(() => {
          return caches.match(req).then((cachedResponse) => {
            return cachedResponse || caches.match('/routine') || caches.match('/study') || caches.match('/');
          });
        })
    );
    return;
  }

  // Handle Static Assets, Media (PDFs/Images), & API (Cache First, Network Fallback)
  event.respondWith(
    caches.match(req).then((cachedResponse) => {
      if (cachedResponse) {
        fetch(req).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(req, networkResponse));
          }
        }).catch(() => {});
        return cachedResponse;
      }
      return fetch(req).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && 
            (req.url.includes('/static/') || req.url.includes('/media/') || req.url.includes('unpkg') || req.url.includes('fonts'))) {
          const copy = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
        }
        return networkResponse;
      }).catch(() => {
        return new Response('', { status: 408, statusText: 'Offline' });
      });
    })
  );
});