/* Service Worker: кэш оболочки приложения «Склад» (офлайн-запуск) */
const CACHE = 'wh-v1';
const ASSETS = ['/warehouse/', '/warehouse/app.js', '/warehouse/manifest.json', '/warehouse/icon-192.png', '/warehouse/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
      const clone = res.clone();
      if (res.ok && new URL(e.request.url).origin === location.origin)
        caches.open(CACHE).then(c => c.put(e.request, clone)).catch(() => {});
      return res;
    }).catch(() => caches.match('/warehouse/')))
  );
});

/* Push-уведомления (Этап 2): новые заказы и оплаты */
self.addEventListener('push', e => {
  let title = 'Склад • Telegram Shop';
  let body = 'Новое уведомление';
  try {
    const data = e.data ? e.data.json() : null;
    if (data && data.title) { title = data.title; body = data.body || ''; }
    else if (e.data) body = e.data.text();
  } catch (err) {
    if (e.data) body = e.data.text();
  }
  e.waitUntil(self.registration.showNotification(title, {
    body, icon: '/warehouse/icon-192.png', badge: '/warehouse/icon-192.png',
    vibrate: [80, 40, 80], tag: 'wh-' + Date.now(),
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    for (const c of list) {
      if ('focus' in c) return c.focus();
    }
    return clients.openWindow('/warehouse/');
  }));
});
