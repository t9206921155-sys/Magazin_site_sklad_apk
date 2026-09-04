/* Service Worker приложения «Склад».
 *
 * Стратегии (Этап 5):
 *   • оболочка (HTML/JS/иконки) — cache-first, чтобы приложение стартовало офлайн;
 *   • GET к /api/... — network-first с фолбэком на кэш: в онлайне всегда свежие
 *     данные, в офлайне — последний известный ответ, помеченный заголовком
 *     X-From-Cache, чтобы UI мог показать «данные могут быть устаревшими»;
 *   • изменяющие запросы (POST/PUT/DELETE) к API в офлайне — складываются в
 *     очередь IndexedDB и повторяются при появлении сети (Background Sync).
 *
 * Раньше здесь был cache-first на ВСЕ GET, включая /api/warehouse/products:
 * склад показывал устаревший список товаров и остатки, а после первой загрузки
 * данные вообще переставали обновляться, пока не сбросишь кэш.
 */
const VERSION = 'wh-v2';
const SHELL_CACHE = VERSION + '-shell';
const API_CACHE = VERSION + '-api';
const ASSETS = [
  '/warehouse/',
  '/warehouse/app.js',
  '/warehouse/manifest.json',
  '/warehouse/icon-192.png',
  '/warehouse/icon-512.png',
];

/* ------------------------------------------------ очередь офлайн-операций */
const DB_NAME = 'wh-offline';
const STORE = 'queue';

function idb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function queueAdd(entry) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).add(entry);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function queueAll() {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

async function queueDelete(id) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function notifyClients(msg) {
  const list = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  for (const c of list) c.postMessage(msg);
}

/** Повторяет отложенные операции. Возвращает {sent, failed, left}. */
async function flushQueue() {
  const items = await queueAll();
  let sent = 0, failed = 0;
  for (const it of items) {
    try {
      const res = await fetch(it.url, {
        method: it.method,
        headers: it.headers,
        body: it.body || undefined,
      });
      if (res.ok || (res.status >= 400 && res.status < 500)) {
        // 4xx повторять бессмысленно (например, товар уже удалён) — снимаем с очереди
        await queueDelete(it.id);
        if (res.ok) sent++; else failed++;
      } else {
        failed++;
      }
    } catch (e) {
      // сети всё ещё нет — оставляем в очереди
      break;
    }
  }
  const left = (await queueAll()).length;
  await notifyClients({ type: 'sync-done', sent, failed, left });
  return { sent, failed, left };
}

/* --------------------------------------------------------------- install */
self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL_CACHE).then(c => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== SHELL_CACHE && k !== API_CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/* ----------------------------------------------------------------- fetch */
function isApi(url) {
  return url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/api/');
}

// Ответы, которые нельзя класть в кэш: настройки с ключами, авторизация.
function isSensitive(url) {
  return /\/(login|settings|quick|webauthn|direct\/config|cloud\/(test|presets))/.test(url.pathname);
}

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);

  if (url.origin !== location.origin) return;

  // 1) Изменяющие запросы к API: при офлайне — в очередь.
  if (req.method !== 'GET') {
    if (!isApi(url)) return;
    e.respondWith((async () => {
      try {
        return await fetch(req.clone());
      } catch (err) {
        // сети нет — сохраняем операцию и отвечаем 202
        const headers = {};
        req.headers.forEach((v, k) => { headers[k] = v; });
        let body = null;
        try { body = await req.clone().text(); } catch (e2) {}
        await queueAdd({
          url: req.url, method: req.method, headers, body, ts: Date.now(),
        });
        if (self.registration.sync) {
          try { await self.registration.sync.register('wh-sync'); } catch (e3) {}
        }
        const left = (await queueAll()).length;
        await notifyClients({ type: 'queued', left });
        return new Response(
          JSON.stringify({ queued: true, offline: true, left,
                           detail: 'Нет сети — операция сохранена и будет отправлена автоматически' }),
          { status: 202, headers: { 'Content-Type': 'application/json' } });
      }
    })());
    return;
  }

  // 2) GET к API: сеть-первой, кэш как аварийный фолбэк.
  if (isApi(url)) {
    e.respondWith((async () => {
      try {
        const res = await fetch(req);
        if (res.ok && !isSensitive(url)) {
          const clone = res.clone();
          caches.open(API_CACHE).then(c => c.put(req, clone)).catch(() => {});
        }
        return res;
      } catch (err) {
        const hit = await caches.match(req);
        if (hit) {
          // помечаем, что данные из кэша — UI покажет предупреждение
          const h = new Headers(hit.headers);
          h.set('X-From-Cache', '1');
          return new Response(await hit.blob(), { status: 200, headers: h });
        }
        return new Response(
          JSON.stringify({ detail: 'Нет сети и нет сохранённой копии' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } });
      }
    })());
    return;
  }

  // 3) Оболочка: кэш-первой.
  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(res => {
      if (res.ok) {
        const clone = res.clone();
        caches.open(SHELL_CACHE).then(c => c.put(req, clone)).catch(() => {});
      }
      return res;
    }).catch(() => caches.match('/warehouse/')))
  );
});

/* --------------------------------------------------- Background Sync */
self.addEventListener('sync', e => {
  if (e.tag === 'wh-sync') e.waitUntil(flushQueue());
});

self.addEventListener('message', e => {
  const d = e.data || {};
  if (d.type === 'flush') e.waitUntil(flushQueue());
  if (d.type === 'queue-size') {
    e.waitUntil(queueAll().then(items => notifyClients({ type: 'queue-size', left: items.length })));
  }
  if (d.type === 'skip-waiting') self.skipWaiting();
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
