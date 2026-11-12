const offlinePage = new URL('static/pwa/offline.html', self.registration.scope).href;
const cachePrefix = 'umshova-offline:' + self.registration.scope + ':';
const cacheName = cachePrefix + '1';

self.addEventListener('install', event => {
    event.waitUntil(caches.open(cacheName).then(cache =>
        cache.add(new Request(offlinePage, { cache: 'reload', credentials: 'omit' }))
    ));
});

self.addEventListener('activate', event => {
    event.waitUntil(caches.keys().then(keys => Promise.all(
        keys.filter(key => key.startsWith(cachePrefix) && key !== cacheName)
            .map(key => caches.delete(key))
    )));
});

self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET' || request.mode !== 'navigate' ||
        !request.url.startsWith(self.registration.scope)) {
        return;
    }

    event.respondWith(fetch(request, { cache: 'no-cache' }).catch(() =>
        caches.open(cacheName)
            .then(cache => cache.match(offlinePage))
            .then(response => response || Response.error())
    ));
});
