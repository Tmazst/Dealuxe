const offlinePage = new URL('static/pwa/offline.html', self.registration.scope).href;
const cachePrefix = 'umshova-offline:' + self.registration.scope + ':';
const cacheName = cachePrefix + '1';

function matchUrl(value) {
    if (typeof value !== 'string') return null;
    const url = new URL(value, self.registration.scope);
    const gamePrefix = new URL('game/', self.registration.scope).href;
    return url.href.startsWith(gamePrefix) ? url.href : null;
}

self.addEventListener('push', event => {
    if (!event.data) return;
    const message = event.data.json();
    const url = matchUrl(message.url);
    if (!url || typeof message.body !== 'string') return;
    event.waitUntil(self.registration.showNotification('uMshova match chat', {
        body: message.body,
        tag: 'match-chat-' + message.id,
        icon: new URL('static/pwa/icon-192.png', self.registration.scope).href,
        data: {url}
    }));
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    const url = matchUrl(event.notification.data && event.notification.data.url);
    if (!url) return;
    event.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(clients => {
        const match = clients.find(client => client.url === url);
        return match ? match.focus() : self.clients.openWindow(url);
    }));
});

self.addEventListener('install', event => {
    event.waitUntil(caches.open(cacheName).then(cache =>
        cache.add(new Request(offlinePage, { cache: 'reload', credentials: 'omit' }))
    ).then(() => self.skipWaiting()));
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
