'use strict';
/* 📦 Склад — мобильный учёт товаров (PWA). Устанавливается на Android как приложение. */
const $ = (s, el) => (el || document).querySelector(s);
const fmt = n => new Intl.NumberFormat('ru-RU').format(n) + ' ₽';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let TOKEN = localStorage.getItem('wh_token') || '';
let PRODUCTS = [];
let EDIT_ID = null;
let EDIT_PHOTOS = [];   // [{src, newData?}]
let PHOTO_COUNT = 0;
let selected = new Set();
let scannerStream = null;
let nativeScanInFlight = false;
let WAREHOUSE_SETTINGS = null;
let DIRECT_CFG = null;
let CURRENT_WAREHOUSE = Number(localStorage.getItem('current_warehouse') || 0);
let WAREHOUSES = [];
async function loadWarehouses() {
  const r = await api('/api/warehouse/warehouses'); WAREHOUSES = r.warehouses || [];
  if (!WAREHOUSES.some(w => w.id === CURRENT_WAREHOUSE)) CURRENT_WAREHOUSE = r.default || (WAREHOUSES[0] && WAREHOUSES[0].id) || 0;
  localStorage.setItem('current_warehouse', CURRENT_WAREHOUSE); renderWarehouseSelector();
}
function renderWarehouseSelector() { const el = $('#warehouse-select'); if (!el) return; el.innerHTML = WAREHOUSES.map(w => `<option value=\"${w.id}\" ${w.id===CURRENT_WAREHOUSE?'selected':''}>${esc(w.name)}</option>`).join(''); el.style.display = WAREHOUSES.length > 1 ? '' : 'none'; }
async function changeWarehouse(id) { CURRENT_WAREHOUSE = Number(id); localStorage.setItem('current_warehouse', CURRENT_WAREHOUSE); renderWarehouseSelector(); await loadList(); }
async function stockBreakdown(pid) { return api(`/api/warehouse/products/${pid}/stock`); }
async function transferStock(pid) { const r=await stockBreakdown(pid); const choices=r.rows.map(x=>`<option value=\"${x.warehouse_id}\">${esc(x.warehouse_name)} (${x.qty})</option>`).join(''); const dst=WAREHOUSES.map(w=>`<option value=\"${w.id}\">${esc(w.name)}</option>`).join(''); const qty=prompt('Количество для перемещения:','1'); if(!qty) return; const from=prompt('ID склада-источника (доступные: '+r.rows.map(x=>x.warehouse_id).join(', ')+')',String(CURRENT_WAREHOUSE)); const to=prompt('ID склада-приёмника',String(WAREHOUSES.find(w=>w.id!==Number(from))?.id||'')); if(!from||!to||from===to)return; await api('/api/warehouse/transfer',{method:'POST',body:JSON.stringify({product_id:pid,from:Number(from),to:Number(to),qty:Number(qty)})}); toast('Перемещение выполнено ✅'); loadList(); }
window.changeWarehouse=changeWarehouse; window.transferStock=transferStock;

function toast(msg, err) {
  const el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 2500);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', 'X-Wh-Token': TOKEN, 'X-Admin-Token': TOKEN, ...(opts.headers || {}) },
  });
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (res.status === 403) { $('#login').classList.remove('hidden'); throw new Error('Нужен вход'); }
  // 202 от service worker: сети нет, операция поставлена в очередь (Этап 5).
  if (res.status === 202 && data && data.queued) {
    OFFLINE_QUEUE = data.left || OFFLINE_QUEUE + 1;
    updateOfflineBar();
    return data;
  }
  if (res.headers.get('X-From-Cache') === '1') {
    LAST_FROM_CACHE = true;
    updateOfflineBar();
  }
  if (!res.ok) throw new Error((data && data.detail) || ('Ошибка ' + res.status));
  return data;
}

let WHOAMI = null;

async function doLogin() {
  try {
    const login = $('#login-inp').value;
    const res = await fetch('/api/warehouse/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login, password: $('#pass').value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Неверный логин или пароль');
    TOKEN = data.token;
    WHOAMI = data;
    WAREHOUSE_SETTINGS = null;
    DIRECT_CFG = null;
    localStorage.setItem('wh_token', TOKEN);
    if ($('#remember').checked) localStorage.setItem('wh_login', login);
    else localStorage.removeItem('wh_login');
    $('#login').classList.add('hidden');
    loadList(); syncTick();
  } catch (e) {
    $('#loginErr').textContent = e.message;
    $('#loginErr').classList.remove('hidden');
  }
}

/* ---------- быстрый вход: PIN (устройство) + биометрия WebAuthn ---------- */
const QUICK_KEY = 'wh_quick';   // {pin:"xxxx", data:"b64", login:"..."}
const WEB_WEBAUTHN = !!(window.PublicKeyCredential) && window.isSecureContext;

function qObfuscate(secret, pin) {
  // простая обфускация PIN-кодом (защита от случайного просмотра localStorage)
  const salt = String(Date.now() % 100000).padStart(5, '0');
  const src = secret + '|' + salt;
  let out = '';
  for (let i = 0; i < src.length; i++) {
    out += String.fromCharCode(src.charCodeAt(i) ^ pin.charCodeAt(i % pin.length));
  }
  return btoa(unescape(encodeURIComponent(out)));
}
function qDeobfuscate(data, pin) {
  try {
    const raw = decodeURIComponent(escape(atob(data)));
    let out = '';
    for (let i = 0; i < raw.length; i++) {
      out += String.fromCharCode(raw.charCodeAt(i) ^ pin.charCodeAt(i % pin.length));
    }
    const [secret, salt] = out.split('|');
    if (!secret || salt === undefined) return '';
    return secret;
  } catch (e) { return ''; }
}
function refreshQuickBox() {
  const box = $('#quickBox');
  if (!box) return;
  const q = (() => { try { return JSON.parse(localStorage.getItem(QUICK_KEY) || 'null'); } catch (e) { return null; } })();
  if (!q) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  $('#quickNote').textContent = '';
  if (q.login) $('#login-inp').value = q.login;
}
async function quickLoginStart() {
  const q = (() => { try { return JSON.parse(localStorage.getItem(QUICK_KEY) || 'null'); } catch (e) { return null; } })();
  if (!q) return;
  if (q.bio === true && WEB_WEBAUTHN) { await quickBioLogin(q.login); return; }
  $('#quickPinBox').classList.remove('hidden');
  $('#quick-pin').focus();
}
async function quickLoginWithPin() {
  const q = (() => { try { return JSON.parse(localStorage.getItem(QUICK_KEY) || 'null'); } catch (e) { return null; } })();
  const pin = $('#quick-pin').value.trim();
  if (!q || !pin) return;
  const secret = qDeobfuscate(q.data, pin);
  if (!secret) { $('#quickNote').textContent = '❌ Неверный PIN'; return; }
  try {
    const res = await fetch('/api/warehouse/quick/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ secret }),
    });
    const data = await res.json();
    if (!res.ok) { $('#quickNote').textContent = data.detail || 'Быстрый вход отключён — войдите по паролю'; $('#quickPinBox').classList.add('hidden'); return; }
    TOKEN = data.token;
    WHOAMI = data.user;
    WAREHOUSE_SETTINGS = null;
    DIRECT_CFG = null;
    localStorage.setItem('wh_token', TOKEN);
    $('#login').classList.add('hidden');
    $('#quick-pin').value = '';
    loadList(); syncTick();
    toast('⚡ Быстрый вход');
  } catch (e) { $('#quickNote').textContent = e.message; }
}
async function quickSetup(pin) {
  // вызывается из настроек: создаёт секрет устройства
  try {
    const r = await api('/api/warehouse/quick/setup', { method: 'POST', body: '{}' });
    const q = { pin: pin, data: qObfuscate(r.secret, pin), login: WHOAMI ? WHOAMI.login : '', bio: false };
    localStorage.setItem(QUICK_KEY, JSON.stringify(q));
    toast('🔓 Быстрый вход по PIN включён');
  } catch (e) { toast(e.message, true); }
}
async function quickDisable() {
  try { await api('/api/warehouse/quick/revoke', { method: 'DELETE', body: '{}' }); } catch (e) {}
  localStorage.removeItem(QUICK_KEY);
  toast('Быстрый вход отключён');
}
async function bioSetup() {
  if (!WEB_WEBAUTHN) {
    toast('Биометрия недоступна: нужен HTTPS и поддержка браузера (Chrome/Safari)', true);
    return;
  }
  try {
    const opts = await api('/api/warehouse/webauthn/register-options', { method: 'POST', body: '{}' });
    const cred = await navigator.credentials.create({ publicKey: opts });
    const json = {
      id: cred.id, rawId: arrayBufferToB64(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: arrayBufferToB64(cred.response.clientDataJSON),
        attestationObject: arrayBufferToB64(cred.response.attestationObject),
      },
      clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
    };
    const r = await api('/api/warehouse/webauthn/register', { method: 'POST', body: JSON.stringify(json) });
    const q = (() => { try { return JSON.parse(localStorage.getItem(QUICK_KEY) || 'null'); } catch (e) { return null; } })() || {};
    q.bio = true;
    localStorage.setItem(QUICK_KEY, JSON.stringify(q));
    toast('👆 Биометрия включена: ' + (r.message || 'вход по отпечатку доступен'));
  } catch (e) { toast(e.message, true); }
}
async function quickBioLogin(login) {
  try {
    const opts = await fetch('/api/warehouse/webauthn/auth-options', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login }),
    }).then(r => r.json());
    if (opts.detail) { $('#quickNote').textContent = opts.detail; $('#quickPinBox').classList.remove('hidden'); return; }
    const cred = await navigator.credentials.get({ publicKey: opts });
    const json = {
      id: cred.id, rawId: arrayBufferToB64(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: arrayBufferToB64(cred.response.clientDataJSON),
        authenticatorData: arrayBufferToB64(cred.response.authenticatorData),
        signature: arrayBufferToB64(cred.response.signature),
        userHandle: cred.response.userHandle ? arrayBufferToB64(cred.response.userHandle) : null,
      },
      clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
    };
    const res = await fetch('/api/warehouse/webauthn/auth', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential: json }),
    });
    const data = await res.json();
    if (!res.ok) { $('#quickNote').textContent = data.detail || 'Не удалось подтвердить'; return; }
    TOKEN = data.token;
    WHOAMI = data.user;
    WAREHOUSE_SETTINGS = null;
    DIRECT_CFG = null;
    localStorage.setItem('wh_token', TOKEN);
    $('#login').classList.add('hidden');
    loadList(); syncTick();
    toast('👆 Вход по биометрии');
  } catch (e) { $('#quickNote').textContent = e.message || 'Биометрия не подтверждена'; }
}
function arrayBufferToB64(buf) {
  let bin = '';
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
window.quickLoginStart = quickLoginStart;
window.quickLoginWithPin = quickLoginWithPin;

function isNativeAndroidApp() {
  try { return !!window.AndroidScanner; } catch (e) { return false; }
}
function canOpenNativeAppSettings() {
  try { return !!(window.AndroidScanner && typeof window.AndroidScanner.canOpenAppSettings === 'function' && window.AndroidScanner.canOpenAppSettings()); }
  catch (e) { return false; }
}
function getNativeAppVersion() {
  try { return window.AndroidScanner && typeof window.AndroidScanner.appVersion === 'function' ? String(window.AndroidScanner.appVersion() || '') : ''; }
  catch (e) { return ''; }
}
function getNativeServerUrl() {
  try { return window.AndroidScanner && typeof window.AndroidScanner.currentServerUrl === 'function' ? String(window.AndroidScanner.currentServerUrl() || '') : ''; }
  catch (e) { return ''; }
}
function openNativeAppSettings() {
  if (!canOpenNativeAppSettings()) return toast('Настройки APK доступны только внутри Android-приложения', true);
  try { window.AndroidScanner.openAppSettings(); }
  catch (e) { toast('Не удалось открыть настройки APK', true); }
}
async function copyText(value, okMsg) {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    toast(okMsg || 'Скопировано');
  } catch (e) {
    prompt('Скопируйте вручную:', value);
  }
}
function copyNativeServerUrl() {
  const url = getNativeServerUrl();
  if (!url) return toast('Адрес склада ещё не сохранён в APK', true);
  copyText(url, 'Адрес склада скопирован');
}
function renderApkSettingsBox() {
  const box = $('#apkSettingsBox');
  const note = $('#apkSettingsNote');
  if (!box || !note) return;
  if (!canOpenNativeAppSettings()) {
    box.classList.add('hidden');
    note.textContent = '';
    return;
  }
  const server = getNativeServerUrl();
  const version = getNativeAppVersion();
  box.classList.remove('hidden');
  note.textContent = (server ? `Текущий адрес склада: ${server}` : 'Адрес склада ещё не задан.')
    + (version ? ` · APK ${version}` : '');
}
window.openNativeAppSettings = openNativeAppSettings;
window.copyNativeServerUrl = copyNativeServerUrl;

// предзаполнение логина (учётные данные сохраняются на устройстве)
const savedLogin = localStorage.getItem('wh_login');
if (savedLogin) $('#login-inp').value = savedLogin;
refreshQuickBox();
renderApkSettingsBox();

function normalizeDbMode(mode, provider) {
  const m = String(mode || '').trim().toLowerCase();
  if (m === 'supabase_direct' || m === 'supabase_proxy' || m === 'vps' || m === 'mysql') return m;
  if (m === 'supabase') return 'supabase_proxy';
  const p = String(provider || '').trim().toLowerCase();
  if (p === 'supabase') return 'supabase_proxy';
  if (p === 'mysql') return 'mysql';
  return 'vps';
}

async function ensureWarehouseSettings(force = false) {
  if (!TOKEN) return null;
  if (force || !WAREHOUSE_SETTINGS) WAREHOUSE_SETTINGS = await api('/api/warehouse/settings');
  return WAREHOUSE_SETTINGS;
}

function currentCloudSettings() {
  return (WAREHOUSE_SETTINGS && WAREHOUSE_SETTINGS.cloud) || {};
}

function currentDbMode() {
  const cloud = currentCloudSettings();
  return normalizeDbMode(cloud.db_mode, cloud.provider);
}

function isDirectMode() {
  return currentDbMode() === 'supabase_direct';
}

function dbModeLabel(mode) {
  if (mode === 'supabase_direct') return 'DIRECT SUPABASE';
  if (mode === 'supabase_proxy') return 'VPS → SUPABASE';
  if (mode === 'mysql') return 'MYSQL';
  return 'VPS';
}

async function ensureDirectConfig(force = false) {
  await ensureWarehouseSettings(force);
  if (!isDirectMode()) { DIRECT_CFG = null; return null; }
  if (force || !DIRECT_CFG) {
    const cfg = await api('/api/warehouse/direct/config');
    if (!cfg || !cfg.enabled) throw new Error('Direct Supabase не настроен');
    DIRECT_CFG = cfg;
  }
  return DIRECT_CFG;
}

function supaHeaders(cfg, write, extra = {}) {
  const key = String((cfg && cfg.key) || '').trim();
  const headers = { apikey: key, ...extra };
  // Modern Supabase publishable/secret keys are passed via apikey only.
  // Legacy anon/service_role JWT keys still work as Bearer.
  if (key && !key.startsWith('sb_publishable_') && !key.startsWith('sb_secret_')) {
    headers.Authorization = 'Bearer ' + key;
  }
  if (cfg.schema && cfg.schema !== 'public') {
    headers['Accept-Profile'] = cfg.schema;
    if (write) headers['Content-Profile'] = cfg.schema;
  }
  return headers;
}

function supaTableUrl(cfg, query = '') {
  return `${cfg.url}/rest/v1/${encodeURIComponent(cfg.table)}${query || ''}`;
}

async function supaRequest(cfg, method, query = '', body = null, extraHeaders = {}) {
  const write = !['GET', 'HEAD'].includes(String(method || 'GET').toUpperCase());
  const res = await fetch(supaTableUrl(cfg, query), {
    method,
    headers: supaHeaders(cfg, write, { 'Content-Type': 'application/json', ...extraHeaders }),
    body: body === null ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error((data && (data.message || data.error_description || data.details || data.hint)) || ('Supabase error ' + res.status));
  return data;
}

function parseMaybeJson(value, fallback) {
  if (Array.isArray(fallback) && Array.isArray(value)) return value;
  if (fallback && typeof fallback === 'object' && !Array.isArray(fallback) && value && typeof value === 'object' && !Array.isArray(value)) return value;
  if (typeof value !== 'string') return fallback;
  try {
    const parsed = JSON.parse(value);
    return parsed == null ? fallback : parsed;
  } catch (e) {
    return fallback;
  }
}

function normalizeDirectProduct(p) {
  const photos = Array.isArray(p.photos) ? p.photos : parseMaybeJson(p.photos, []);
  const params = (p.params && typeof p.params === 'object' && !Array.isArray(p.params)) ? p.params : parseMaybeJson(p.params, {});
  const stock = Number(p.stock ?? -1);
  const price = Number(p.price ?? 0);
  const photo = p.photo || photos[0] || '/webapp/img/products/placeholder.jpg';
  return {
    id: Number(p.id || 0),
    code: String(p.code || ''),
    barcode: String(p.barcode || ''),
    name: String(p.name || ''),
    category: String(p.category || ''),
    storage_location: String(p.storage_location || ''),
    owner_name: String(p.owner_name || ''),
    stock,
    price,
    old_price: Number(p.old_price ?? 0),
    purchase_price: Number(p.purchase_price ?? 0),
    description: String(p.description || ''),
    is_archived: !!p.is_archived,
    sum: stock < 0 ? price : price * stock,
    on_showcase: !(p.on_showcase === false || p.on_showcase === 0 || p.on_showcase === 'false'),
    in_stock: !(p.in_stock === false || p.in_stock === 0 || p.in_stock === 'false'),
    photos: photos.map(x => String(x || '')).filter(Boolean),
    photo: String(photo),
    photo_local: String(p.photo || ''),
    seller_id: Number(p.seller_id || 0),
    condition: String(p.condition || 'new'),
    subcategory: String(p.subcategory || ''),
    params,
  };
}

function toDirectRow(p) {
  return {
    id: Number(p.id || 0),
    code: String(p.code || ''),
    name: String(p.name || ''),
    category: String(p.category || ''),
    price: Number(p.price || 0),
    old_price: Number(p.old_price || 0),
    stock: Number(p.stock ?? -1),
    description: String(p.description || ''),
    photo: String(p.photo || ''),
    photos: Array.isArray(p.photos) ? p.photos.map(x => String(x || '')).filter(Boolean) : [],
    storage_location: String(p.storage_location || ''),
    owner_name: String(p.owner_name || ''),
    barcode: String(p.barcode || ''),
    on_showcase: !!p.on_showcase,
    in_stock: !!p.in_stock,
    purchase_price: Number(p.purchase_price || 0),
    is_archived: !!p.is_archived,
    condition: String(p.condition || 'new'),
    subcategory: String(p.subcategory || ''),
    params: (p.params && typeof p.params === 'object' && !Array.isArray(p.params)) ? p.params : {},
  };
}

function filterWarehouseProducts(list, q) {
  if (!q || !q.trim()) return list;
  const ql = q.trim().toLowerCase();
  return list.filter(p =>
    String(p.name || '').toLowerCase().includes(ql) ||
    String(p.code || '').toLowerCase().includes(ql) ||
    String(p.barcode || '').toLowerCase().includes(ql) ||
    String(p.storage_location || '').toLowerCase().includes(ql) ||
    String(p.owner_name || '').toLowerCase().includes(ql)
  );
}

async function directLoadProducts(q = '') {
  const cfg = await ensureDirectConfig();
  const rows = await supaRequest(cfg, 'GET', '?select=*&order=id.asc');
  const products = filterWarehouseProducts((rows || []).map(normalizeDirectProduct).filter(p => !p.is_archived), q);
  return { products, stats: { products: products.length } };
}

async function directNextId() {
  const r = await api('/api/warehouse/direct/next-id', { method: 'POST', body: '{}' });
  return Number(r.id || 0);
}

async function directPreparePhotos(photos) {
  return api('/api/warehouse/direct/photos', { method: 'POST', body: JSON.stringify({ photos }) });
}

async function mirrorDirectProduct(product, action, details, scan) {
  return api('/api/warehouse/direct/mirror', {
    method: 'POST',
    body: JSON.stringify({ product: toDirectRow(product), action, details, scan }),
  });
}

async function mirrorDirectDelete(productId, action, details) {
  return api('/api/warehouse/direct/mirror', {
    method: 'POST',
    body: JSON.stringify({ delete: true, product_id: productId, action, details }),
  });
}

async function directUpsertProducts(products) {
  const cfg = await ensureDirectConfig();
  const payload = products.map(toDirectRow);
  const data = await supaRequest(cfg, 'POST', '?on_conflict=id&select=*', payload, { 'Prefer': 'resolution=merge-duplicates,return=representation' });
  return (Array.isArray(data) ? data : payload).map(normalizeDirectProduct);
}

async function directSaveOne(product, meta = {}) {
  const saved = (await directUpsertProducts([product]))[0] || normalizeDirectProduct(product);
  await mirrorDirectProduct(saved, meta.action || 'синхронизировал товар (direct)', meta.details || '', meta.scan || null);
  return saved;
}

async function directDeleteOne(product) {
  const cfg = await ensureDirectConfig();
  await supaRequest(cfg, 'DELETE', `?id=eq.${encodeURIComponent(product.id)}&select=id`, null, { 'Prefer': 'return=representation' });
  await mirrorDirectDelete(product.id, 'удалил товар (direct)', `${product.name} (id ${product.id})`);
}

async function directBulkSave(products, patchKeys = []) {
  const saved = await directUpsertProducts(products);
  await api('/api/warehouse/direct/mirror-bulk', {
    method: 'POST',
    body: JSON.stringify({ products: saved.map(toDirectRow), patch_keys: patchKeys, action: 'массовое редактирование (direct)' }),
  });
  return saved;
}

/* ---------- список ---------- */
async function loadList() {
  try {
    await ensureWarehouseSettings();
    await loadWarehouses();
    const q = $('#q').value.trim();
    const r = isDirectMode()
      ? await directLoadProducts(q)
      : await api('/api/warehouse/products' + (q ? '?q=' + encodeURIComponent(q) : ''));
    PRODUCTS = r.products || [];
    $('#cnt').textContent = PRODUCTS.length + ' поз.';
    renderList();
  } catch (e) { /* вход */ }
}

function renderList() {
  const el = $('#list');
  if (!PRODUCTS.length) {
    el.innerHTML = '<div style="text-align:center;color:#64748b;padding:40px 10px">Ничего не найдено.<br>Добавьте первый товар кнопкой ＋</div>';
    return;
  }
  el.innerHTML = PRODUCTS.map(p => `
    <div class="card">
      <input type="checkbox" class="chk" data-id="${p.id}" ${selected.has(String(p.id)) ? 'checked' : ''} onchange="toggleSel(${p.id}, this.checked)">
      <img src="${esc(p.photo || '/webapp/img/products/placeholder.jpg')}" onclick="openForm(${p.id})">
      <div class="info">
        <div class="name">${esc(p.name)}</div>
        <div class="meta">
          ${p.code ? 'Арт: <b>' + esc(p.code) + '</b> · ' : ''}${p.barcode ? 'ШК: ' + esc(p.barcode) + ' · ' : ''}
          📍 ${esc(p.storage_location || '—')} · 👤 ${esc(p.owner_name || '—')}<br>
          📷 ${p.photos.length} фото · ${p.category || ''}
        </div>
        <div class="row">
          <div><span class="price">${fmt(p.price)}</span> <span class="sum">× ${p.stock < 0 ? '∞' : p.stock} = ${p.stock < 0 ? '—' : fmt(p.sum)}</span></div>
          <span class="switch"><input type="checkbox" ${p.on_showcase ? 'checked' : ''} onchange="toggleShowcase(${p.id}, this.checked)"><span class="sl"></span></span>
          <span class="badge ${p.on_showcase ? 'on' : 'off'}">${p.on_showcase ? '🟢 витрина' : '⚪ склад'}</span>
        </div>
        <div class="actions">
          <button class="mini" onclick="openForm(${p.id})">✏️</button>
          <button class="mini" onclick="copyOne(${p.id})">⧉</button>
          <button class="mini" onclick="printOne(${p.id})">🖨</button>
          <button class="mini" onclick="publishOne(${p.id})">📣</button>
          <button class="mini" onclick="archiveOne(${p.id})">🗄</button>
          <button class="mini" onclick="showStock(${p.id})">📊</button>
        </div>
      </div>
    </div>`).join('');
  $('#printBtn').classList.toggle('active', selected.size > 0);
  $('#bulkBtn').classList.toggle('active', selected.size > 0);
}

async function showStock(id) { try { const r=await stockBreakdown(id); alert(r.rows.map(x=>`${x.warehouse_name}: ${x.qty}`).join('\n')+'\nИтого: '+r.total); } catch(e){toast(e.message,true);} }
function toggleSel(id, on) {
  if (on) selected.add(String(id)); else selected.delete(String(id));
  $('#printBtn').classList.toggle('active', selected.size > 0);
  $('#bulkBtn').classList.toggle('active', selected.size > 0);
}

async function toggleShowcase(id, on) {
  try {
    if (isDirectMode()) {
      const src = PRODUCTS.find(x => x.id === id);
      if (!src) throw new Error('Товар не найден');
      await directSaveOne({ ...src, on_showcase: on }, {
        action: 'изменил товар (direct)',
        details: `${src.name} (id ${src.id})`,
      });
    } else {
      await api('/api/warehouse/products/' + id, { method: 'PUT', body: JSON.stringify({ on_showcase: on }) });
    }
    toast(on ? 'Выставлено на витрину 🟢' : 'Снято с витрины');
    loadList();
    loadCloudStatus();
  } catch (e) { toast(e.message, true); }
}

/* ---------- форма ---------- */
async function openForm(id) {
  EDIT_ID = id || null;
  EDIT_PHOTOS = [];
  if (id) {
    const p = PRODUCTS.find(x => x.id === id) || await api('/api/warehouse/products/' + id).then(r => r.products[0]).catch(() => null);
    if (p) {
      $('#f-name').value = p.name; $('#f-code').value = p.code; $('#f-barcode').value = p.barcode;
      $('#f-location').value = p.storage_location; $('#f-owner').value = p.owner_name;
      $('#f-qty').value = p.stock < 0 ? '' : p.stock; $('#f-price').value = p.price;
      $('#f-purchase').value = p.purchase_price || '';
      $('#f-cat').value = p.category; $('#f-desc').value = ''; $('#f-desc').value = p.description || '';
      $('#f-showcase').checked = !!p.on_showcase;
      EDIT_PHOTOS = (p.photos || []).map(src => ({ src }));
    }
    $('#form-title').textContent = 'Изменить товар';
    $('#delBtn').classList.remove('hidden');
  } else {
    ['f-name','f-code','f-barcode','f-location','f-owner','f-qty','f-price','f-cat','f-desc','f-purchase'].forEach(i => $('#' + i).value = '');
    $('#f-showcase').checked = true;
    $('#form-title').textContent = 'Новый товар';
    $('#delBtn').classList.add('hidden');
  }
  renderPhotos();
  $('#sheet').classList.remove('hidden');
}

function closeForm() { $('#sheet').classList.add('hidden'); }

function renderPhotos() {
  $('#photos').innerHTML = EDIT_PHOTOS.map((ph, i) => `
    <div class="phwrap">
      <img src="${ph.newData || ph.src}">
      <button class="phdel" onclick="delPhoto(${i})">✕</button>
    </div>`).join('')
    + (EDIT_PHOTOS.length < 20 ? `<button class="phadd" onclick="addPhoto('choose')">＋<br>${EDIT_PHOTOS.length}/20</button>` : '');
}

function delPhoto(i) { EDIT_PHOTOS.splice(i, 1); renderPhotos(); }

async function addPhoto(kind) {
  if (EDIT_PHOTOS.length >= 20) return toast('Максимум 20 фото', true);
  if (kind === 'url') {
    const url = prompt('Ссылка на фото из интернета:');
    if (url) { EDIT_PHOTOS.push({ src: url, newData: url }); renderPhotos(); }
    return;
  }
  if (kind === 'camera') {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = 'image/*'; input.capture = 'environment';
    input.onchange = e => readFiles(e.target.files);
    input.click();
    return;
  }
  if (kind === 'file' || kind === 'choose') {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = 'image/*'; input.multiple = true;
    input.onchange = e => readFiles(e.target.files);
    input.click();
    return;
  }
}

function readFiles(files) {
  for (const f of files) {
    if (EDIT_PHOTOS.length >= 20) break;
    const fr = new FileReader();
    fr.onload = () => { EDIT_PHOTOS.push({ src: fr.result, newData: fr.result }); renderPhotos(); };
    fr.readAsDataURL(f);
  }
}

async function saveProduct() {
  const name = $('#f-name').value.trim();
  const price = +$('#f-price').value;
  if (!name) return toast('Укажите наименование', true);
  if (!price || price <= 0) return toast('Укажите цену', true);
  const body = {
    name, code: $('#f-code').value.trim(), barcode: $('#f-barcode').value.trim(),
    storage_location: $('#f-location').value.trim(), owner_name: $('#f-owner').value.trim(),
    stock: $('#f-qty').value === '' ? -1 : +$('#f-qty').value, price,
    purchase_price: +$('#f-purchase').value || 0,
    category: $('#f-cat').value.trim() || 'Прочее', description: $('#f-desc').value.trim(),
    on_showcase: $('#f-showcase').checked,
    in_stock: ($('#f-qty').value === '' ? true : (+$('#f-qty').value > 0)),
    photos: EDIT_PHOTOS.map(ph => ph.newData || ph.src),
  };
  try {
    let pid = EDIT_ID;
    if (isDirectMode()) {
      const prepared = await directPreparePhotos(body.photos);
      const existing = EDIT_ID ? (PRODUCTS.find(x => x.id === EDIT_ID) || {}) : {};
      const product = {
        ...existing,
        ...body,
        id: EDIT_ID || await directNextId(),
        photos: prepared.photos || [],
        photo: prepared.photo || '',
        is_archived: !!existing.is_archived,
      };
      const saved = await directSaveOne(product, {
        action: EDIT_ID ? 'изменил товар (direct)' : 'создал товар (direct)',
        details: `${name} (id ${product.id})`,
      });
      pid = saved.id;
    } else if (EDIT_ID) {
      await api('/api/warehouse/products/' + EDIT_ID, { method: 'PUT', body: JSON.stringify(body) });
    } else {
      const created = await api('/api/warehouse/products', { method: 'POST', body: JSON.stringify(body) });
      pid = created.id;
    }
    if ($('#f-publish').checked && pid) {
      try {
        const pub = await api(`/api/warehouse/products/${pid}/publish`, { method: 'POST', body: '{}' });
        const done = Object.entries(pub).filter(([k, v]) => v && v.ok).length;
        toast(done ? `Опубликовано в ${done} канал(ах) 📣` : 'Публикация: проверьте настройки каналов');
      } catch (e) { toast('Опубликовать не удалось: ' + e.message, true); }
    }
    toast('Сохранено ✅');
    closeForm(); loadList();
  } catch (e) { toast(e.message, true); }
}

async function publishOne(id) {
  toast('Публикуем…');
  try {
    const res = await api(`/api/warehouse/products/${id}/publish`, { method: 'POST', body: '{}' });
    const parts = Object.entries(res).map(([k, v]) => k + (v && v.ok ? ' ✅' : ' ⚠️')).join(', ');
    toast('Каналы: ' + (parts || 'не настроены'));
  } catch (e) { toast(e.message, true); }
}

async function exportOne(id) {
  try {
    await downloadAuthed(`/api/warehouse/labels.pdf?ids=${id}`, 'label.pdf', true);
  } catch (e) { toast(e.message, true); }
}

async function copyOne(id) {
  try {
    if (isDirectMode()) {
      const src = PRODUCTS.find(x => x.id === id);
      if (!src) throw new Error('Товар не найден');
      const base = src.code || `TG-${src.id}`;
      let i = 2;
      let newCode = `${base}-${i}`;
      const existingCodes = new Set(PRODUCTS.map(p => String(p.code || '')));
      while (existingCodes.has(newCode)) { i += 1; newCode = `${base}-${i}`; }
      const copy = { ...src, id: await directNextId(), code: newCode, is_archived: false };
      await directSaveOne(copy, {
        action: 'создал копию товара (direct)',
        details: `${copy.name} (id ${copy.id})`,
      });
      toast(`Копия создана: ${newCode} ✅`);
    } else {
      const c = await api(`/api/warehouse/products/${id}/copy`, { method: 'POST', body: '{}' });
      toast(`Копия создана: ${c.code} ✅`);
    }
    loadList();
    loadCloudStatus();
  } catch (e) { toast(e.message, true); }
}

async function archiveOne(id) {
  if (!confirm('Отправить товар в архив? (мягкое удаление — можно восстановить в админ-панели сайта)')) return;
  try {
    if (isDirectMode()) {
      const src = PRODUCTS.find(x => x.id === id);
      if (!src) throw new Error('Товар не найден');
      await directSaveOne({ ...src, is_archived: true, in_stock: false }, {
        action: 'архивировал товар (direct)',
        details: `${src.name} (id ${src.id})`,
      });
    } else {
      await api(`/api/warehouse/products/${id}/archive`, { method: 'POST', body: '{}' });
    }
    toast('В архиве 🗄');
    loadList();
    loadCloudStatus();
  } catch (e) { toast(e.message, true); }
}

async function delProduct() {
  if (!EDIT_ID) return;
  if (!confirm('Удалить товар?')) return;
  try {
    if (isDirectMode()) {
      const src = PRODUCTS.find(x => x.id === EDIT_ID) || { id: EDIT_ID, name: 'Товар' };
      await directDeleteOne(src);
    } else {
      await api('/api/warehouse/products/' + EDIT_ID, { method: 'DELETE' });
    }
    toast('Удалён 🗑');
    closeForm(); loadList();
  } catch (e) { toast(e.message, true); }
}

/* ---------- ИИ ---------- */
async function aiGen(mode) {
  if (!EDIT_ID) return toast('Сначала сохраните товар, затем вызовите ИИ', true);
  const p = PRODUCTS.find(x => x.id === EDIT_ID);
  if (!p) return toast('Товар не найден', true);
  toast('ИИ генерирует…');
  try {
    const r = await api('/api/warehouse/ai', { method: 'POST', body: JSON.stringify({ product_id: EDIT_ID, mode }) });
    if (mode === 'title') {
      $('#f-name').value = (r.titles && r.titles[0]) || $('#f-name').value;
      toast('Названия готовы — первый вариант подставлен. Остальные: ' + ((r.titles || []).slice(1).join(' / ') || '—'));
    } else if (mode === 'listing') {
      $('#f-desc').value = r.text || $('#f-desc').value;
      toast('Текст объявления подставлен в описание ✅');
    } else {
      const label = mode === 'vk' ? 'VK' : mode === 'instagram' ? 'Instagram' : 'Telegram';
      const text = (r.text || '') + '\n\n' + ((r.hashtags || []).join(' '));
      try { await navigator.clipboard.writeText(text); } catch (e) {}
      prompt('Пост для ' + label + ' (скопирован в буфер):', text);
      toast('Пост для ' + label + ' готов 📣');
    }
  } catch (e) { toast(e.message, true); }
}

/* ---------- сканер (BarcodeDetector + native Android fallback) ---------- */
let SCAN_MODE = 'search';

function hasNativeAndroidScanner() {
  try {
    return !!(window.AndroidScanner && typeof window.AndroidScanner.isNativeScannerAvailable === 'function'
      && window.AndroidScanner.isNativeScannerAvailable());
  } catch (e) {
    return false;
  }
}

function startNativeAndroidScan(mode) {
  if (!hasNativeAndroidScanner()) return false;
  try {
    nativeScanInFlight = true;
    window.AndroidScanner.startScan(mode || SCAN_MODE);
    toast('Открываю нативный сканер Android…');
    return true;
  } catch (e) {
    nativeScanInFlight = false;
    toast('Не удалось открыть нативный сканер: ' + (e.message || e), true);
    return false;
  }
}

window.__nativeScanResult = async function (code, mode) {
  nativeScanInFlight = false;
  if (mode) SCAN_MODE = mode;
  if (!code) return;
  toast('Код считан нативным сканером');
  await handleScanCode(String(code).trim());
};

window.__nativeScanCancelled = function () {
  if (!nativeScanInFlight) return;
  nativeScanInFlight = false;
  toast('Сканирование отменено');
};

async function openScanModes() {
  $('#sheet2-title').textContent = '📷 Сканер: выберите режим';
  $('#sheet2-body').innerHTML = `
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;padding:10px 12px;margin-bottom:10px;color:#1d4ed8;font-size:12.5px">Поддерживаются EAN-13, EAN-8, Code 128, Code 39 и QR. В Android APK камера запросится автоматически, а при нестабильном WebView-сканере приложение переключится на нативный Android fallback.</div>
    <div class="card" style="align-items:center" onclick="pickScanMode('search'); closeSheet2()">
      <div class="info"><div class="name">🔍 Поиск</div><div class="meta">Сканировать штрих-код/QR → открыть карточку</div></div>
    </div>
    <div class="card" style="align-items:center" onclick="pickScanMode('receive'); closeSheet2()">
      <div class="info"><div class="name">➕ Приёмка</div><div class="meta">Сканировать штрих-код/QR → остаток +1</div></div>
    </div>
    <div class="card" style="align-items:center" onclick="pickScanMode('sell'); closeSheet2()">
      <div class="info"><div class="name">➖ Продажа</div><div class="meta">Сканировать штрих-код/QR → остаток −1 (предупреждение при 0)</div></div>
    </div>
    <div class="card" style="align-items:center" onclick="pickScanMode('inventory'); closeSheet2()">
      <div class="info"><div class="name">🧮 Инвентаризация</div><div class="meta">Сканировать штрих-код/QR → ввести фактический остаток</div></div>
    </div>
    <div class="card" style="align-items:center" onclick="closeSheet2(); openVision()">
      <div class="info"><div class="name">🤖 ИИ-vision</div><div class="meta">Сфотографировать → найти карточку товара (Этап 3)</div></div>
    </div>
    <div class="card" style="align-items:center" onclick="closeSheet2(); openInventoryCompare()">
      <div class="info"><div class="name">🧮 Инвентаризация со сверкой</div><div class="meta">Сравнить фактические остатки с базой (Этап 3)</div></div>
    </div>
    <div class="card" style="align-items:center" onclick="closeSheet2(); openScanHistory()">
      <div class="info"><div class="name">📜 История сканирований</div><div class="meta">Последние 50 операций</div></div>
    </div>
    <div class="card" style="align-items:center" onclick="closeSheet2(); openHidScanMode()">
      <div class="info"><div class="name">📶 Bluetooth / ТСД (HID)</div><div class="meta">Сканер как клавиатура: авто-приём кода</div></div>
    </div>`;
  $('#sheet2').classList.remove('hidden');
}

function pickScanMode(mode) { SCAN_MODE = mode; startScan(); }

async function openScanHistory() {
  try {
    const r = await api('/api/warehouse/scans');
    $('#sheet2-title').textContent = '📜 История сканирований';
    $('#sheet2-body').innerHTML = r.scans.length ? r.scans.map(s => `
      <div class="card" style="align-items:center">
        <div class="info">
          <div class="name">${['🔍','➕','➖','🧮'][['search','receive','sell','inventory'].indexOf(s.mode)] || '📷'}
            ${esc(r.product_names[String(s.product_id)] || s.code || '—')}</div>
          <div class="meta">${esc(s.result)} · ${esc(s.user_name)} · ${new Date(s.ts).toLocaleString('ru-RU')}</div>
        </div>
      </div>`).join('') : '<p style="color:#64748b">Сканирований ещё не было</p>';
    $('#sheet2').classList.remove('hidden');
  } catch (e) { toast(e.message, true); }
}

async function startScan() {
  const nativeAvailable = hasNativeAndroidScanner();
  if (!('BarcodeDetector' in window)) {
    if (nativeAvailable && startNativeAndroidScan(SCAN_MODE)) return;
    const code = prompt('Сканер не поддерживается этим браузером или WebView.\nВведите штрих-код, QR-значение или артикул вручную:');
    if (code) await handleScanCode(code.trim());
    return;
  }
  $('#cam').classList.remove('hidden');
  try {
    scannerStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    $('#video').srcObject = scannerStream;
    const detector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'qr_code'] });
    const tick = async () => {
      if (!scannerStream) return;
      try {
        const codes = await detector.detect($('#video'));
        if (codes.length) {
          const v = codes[0].rawValue;
          stopScan();
          await handleScanCode(v);
          return;
        }
      } catch (e) {
        if (nativeAvailable && /not implemented|not supported|BarcodeDetector|IllegalState|AbortError/i.test(String(e && e.message))) {
          stopScan();
          toast('WebView-сканер нестабилен, переключаюсь на нативный Android-сканер.');
          startNativeAndroidScan(SCAN_MODE);
          return;
        }
      }
      requestAnimationFrame(tick);
    };
    tick();
  } catch (e) {
    stopScan();
    if (nativeAvailable && /NotReadableError|TrackStartError|AbortError|SecurityError|permission|denied/i.test(String(e && e.message))) {
      toast('WebView не дал стабильный доступ к камере — открываю нативный Android-сканер.');
      startNativeAndroidScan(SCAN_MODE);
      return;
    }
    const suffix = /permission|denied|SecurityError/i.test(String(e && e.message))
      ? ' Разрешите доступ к камере в браузере или в настройках Android-приложения.'
      : '';
    toast('Нет доступа к камере: ' + e.message + suffix, true);
  }
}


async function handleScanCode(code) {
  try {
    let qty = 1;
    if (SCAN_MODE === 'inventory') {
      const input = prompt('Фактический остаток для ' + code + ':');
      if (input === null) return;
      qty = +input || 0;
    }
    if (isDirectMode()) {
      const product = PRODUCTS.find(p => String(p.barcode || '') === code || String(p.code || '') === code);
      if (!product) {
        toast('Товар с таким кодом не найден', true);
        return;
      }
      let message = '', warning = false;
      let next = { ...product };
      if (SCAN_MODE === 'search') {
        message = `Найден: ${product.name}`;
      } else if (SCAN_MODE === 'receive') {
        const newStock = (product.stock >= 0 ? product.stock : 0) + qty;
        next.stock = newStock; next.in_stock = true;
        message = `Приёмка +${qty} → остаток ${newStock}`;
      } else if (SCAN_MODE === 'sell') {
        const cur = product.stock;
        if (cur <= 0) {
          message = `⚠️ ${product.name}: остаток 0 — продажа невозможна`;
          warning = true;
        } else {
          const newStock = Math.max(0, cur - qty);
          next.stock = newStock; next.in_stock = newStock > 0;
          message = `Продажа −${qty} → остаток ${newStock}`;
          warning = newStock === 0;
        }
      } else if (SCAN_MODE === 'inventory') {
        next.stock = Math.max(0, qty); next.in_stock = qty > 0;
        message = `Инвентаризация: остаток установлен ${Math.max(0, qty)}`;
      }
      if (SCAN_MODE === 'search') {
        await mirrorDirectProduct(product, 'сканирование (direct)', `${product.name} (id ${product.id})`,
          { mode: SCAN_MODE, code, qty, result: message });
      } else if (!warning) {
        await directSaveOne(next, {
          action: 'сканирование (direct)',
          details: `${product.name} (id ${product.id})`,
          scan: { mode: SCAN_MODE, code, qty, result: message },
        });
      }
      toast((warning ? '⚠️ ' : '') + message, warning);
      if (SCAN_MODE === 'search') openForm(product.id);
    } else {
      const r = await api('/api/warehouse/scan', { method: 'POST',
        body: JSON.stringify({ code, mode: SCAN_MODE, qty, warehouse_id: CURRENT_WAREHOUSE }) });
      toast((r.warning ? '⚠️ ' : '') + r.message, !r.found || r.warning);
      if (SCAN_MODE === 'search' && r.found) openForm(r.product.id);
    }
    loadList();
    loadCloudStatus();
  } catch (e) { toast(e.message, true); }
}

function stopScan() {
  if (scannerStream) { scannerStream.getTracks().forEach(t => t.stop()); scannerStream = null; }
  $('#cam').classList.add('hidden');
}

/* ---------- наклейки ---------- */
/* кнопки */
$('#saveBtn').addEventListener('click', saveProduct);
$('#delBtn').addEventListener('click', delProduct);
/* ---------- офлайн-режим и очередь операций (Этап 5) ---------- */
let OFFLINE_QUEUE = 0;
let LAST_FROM_CACHE = false;

function renderSyncBar(text, mode) {
  const el = $('#syncbar');
  if (!el) return;
  const colors = {
    online:  ['#0b5c56', '#d7f5f0'],
    offline: ['#7c2d12', '#fed7aa'],
    queued:  ['#78350f', '#fde68a'],
  };
  const [bg, fg] = colors[mode] || colors.online;
  el.style.background = bg;
  el.style.color = fg;
  el.textContent = text;
}

function updateOfflineBar() {
  if (!navigator.onLine) {
    renderSyncBar(
      `📴 Нет сети — работаем офлайн${OFFLINE_QUEUE ? ` · в очереди: ${OFFLINE_QUEUE}` : ''}`,
      'offline');
    return true;
  }
  if (OFFLINE_QUEUE) {
    renderSyncBar(`⏳ Отправляем отложенные операции: ${OFFLINE_QUEUE}`, 'queued');
    return true;
  }
  return false;
}

function askQueueSize() {
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({ type: 'queue-size' });
  }
}

function flushOfflineQueue() {
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({ type: 'flush' });
  }
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('message', ev => {
    const d = ev.data || {};
    if (d.type === 'queued') {
      OFFLINE_QUEUE = d.left || 0;
      updateOfflineBar();
      toast('📴 Нет сети — операция сохранена, отправим автоматически');
    }
    if (d.type === 'queue-size') {
      OFFLINE_QUEUE = d.left || 0;
      updateOfflineBar();
    }
    if (d.type === 'sync-done') {
      OFFLINE_QUEUE = d.left || 0;
      if (d.sent) {
        toast(`✅ Отправлено отложенных операций: ${d.sent}` +
              (d.failed ? ` · отклонено: ${d.failed}` : ''));
        if (typeof loadList === 'function') loadList();
      }
      if (!OFFLINE_QUEUE) syncTick();
      else updateOfflineBar();
    }
  });
}

window.addEventListener('online', () => {
  toast('🌐 Сеть появилась — синхронизируем');
  flushOfflineQueue();
  syncTick();
});
window.addEventListener('offline', () => updateOfflineBar());

async function syncTick() {
  if (updateOfflineBar()) return;
  try {
    const r = await fetch('/api/warehouse/sync', { headers: { 'X-Wh-Token': TOKEN, 'X-Admin-Token': TOKEN } });
    if (!r.ok) return;
    LAST_FROM_CACHE = r.headers.get('X-From-Cache') === '1';
    const d = await r.json();
    const t = new Date(d.server_time).toLocaleTimeString('ru-RU');
    if (LAST_FROM_CACHE) {
      renderSyncBar(`⚠️ Данные из кэша · ${d.products} товаров · на ${t}`, 'offline');
    } else {
      renderSyncBar(`☁️ единая база · ${d.products} товаров · синхронизировано ${t}`, 'online');
    }
  } catch (e) {
    updateOfflineBar();
  }
}

// диалог печати: профили принтеров
async function printLabels() {
  const ids = [...selected];
  if (!ids.length) return toast('Отметьте товары чекбоксами', true);
  try {
    const printers = await fetch('/api/warehouse/printers', { headers: { 'X-Wh-Token': TOKEN, 'X-Admin-Token': TOKEN } }).then(r => r.json());
    $('#sheet2-title').textContent = '🖨 Печать наклеек';
    $('#sheet2-body').innerHTML = `
      <div class="row2" style="margin-bottom:10px">
        <input class="fld" id="pf-cat" placeholder="Фильтр: категория (или пусто)" style="margin:0">
        <input class="fld" id="pf-loc" placeholder="Место (А-3)" style="margin:0">
      </div>
      <button class="btn primary" onclick="printByFilter()" style="margin-bottom:8px">🖨 Печать по фильтру (все подходящие)</button>
      <button class="btn ghost" onclick="printPriceTags()" style="margin-bottom:12px">🏷 Ценники для зала (PDF)</button>
    ` + printers.map((pr, i) => `
      <div class="card" style="align-items:center">
        <div class="info">
          <div class="name">${esc(pr.name)}</div>
          <div class="meta">${pr.width_mm}×${pr.height_mm} мм · ${pr.format.toUpperCase()}</div>
        </div>
        <button class="mini" onclick="printWithPrinter(${i})">Печать</button>
      </div>`).join('');
    $('#sheet2').classList.remove('hidden');
  } catch (e) { toast(e.message, true); }
}

async function printWithPrinter(i) {
  const ids = [...selected];
  if (!ids.length) return toast('Отметьте товары чекбоксами', true);
  try {
    const printers = await fetch('/api/warehouse/printers', { headers: { 'X-Wh-Token': TOKEN, 'X-Admin-Token': TOKEN } }).then(r => r.json());
    const pr = printers[i];
    if (!pr) return toast('Профиль принтера не найден', true);
    const q = `ids=${ids.join(',')}&width=${pr.width_mm}&height=${pr.height_mm}&copies=${pr.copies || 1}`;
    if (pr.format === 'zpl' || pr.format === 'epl') {
      const raw = await fetch(`/api/warehouse/labels.prn?${q}&format=${pr.format}`, {headers:{'X-Wh-Token':TOKEN,'X-Admin-Token':TOKEN}}).then(r=>r.text());
      if (pr.host) { const r=await api('/api/warehouse/print/network',{method:'POST',body:JSON.stringify({host:pr.host,port:pr.port||9100,format:pr.format,data:raw})}); toast('Отправлено на принтер ✅ ('+r.bytes+' байт)'); } else { await downloadAuthed(`/api/warehouse/labels.prn?${q}&format=${pr.format}`, 'labels.prn', false); toast('Файл .prn скачан — укажите IP для прямой печати'); }
    } else {
      await downloadAuthed(`/api/warehouse/labels.pdf?${q}`, 'labels.pdf', true);
      toast('PDF готов — печатайте через диалог принтера');
    }
    closeSheet2();
  } catch (e) { toast(e.message, true); }
}

function printOne(id) {
  selected = new Set([String(id)]);
  printLabels();
}

/* ---------- массовое редактирование (Этап 2) ---------- */
function openBulkEdit() {
  if (!selected.size) return toast('Отметьте товары чекбоксами', true);
  $('#bulk-count').textContent = selected.size;
  ['bk-price', 'bk-purchase', 'bk-location', 'bk-owner', 'bk-category', 'bk-stock'].forEach(id => { $('#' + id).value = ''; });
  $('#bk-showcase').checked = false;
  $('#bk-instock').checked = false;
  $('#sheet3').classList.remove('hidden');
}
function closeBulk() { $('#sheet3').classList.add('hidden'); }
window.closeBulk = closeBulk;
async function applyBulk() {
  const patch = {};
  const num = (id, key) => { const v = $('#' + id).value; if (v !== '') patch[key] = +v || 0; };
  const str = (id, key) => { const v = $('#' + id).value.trim(); if (v !== '') patch[key] = v; };
  num('bk-price', 'price'); num('bk-purchase', 'purchase_price'); num('bk-stock', 'stock');
  str('bk-location', 'storage_location'); str('bk-owner', 'owner_name'); str('bk-category', 'category');
  if ($('#bk-showcase').checked) patch.on_showcase = true;
  if ($('#bk-instock').checked) patch.in_stock = true;
  if (!Object.keys(patch).length) return toast('Ничего не выбрано для изменения', true);
  try {
    if (isDirectMode()) {
      const ids = [...selected].map(Number);
      const changed = PRODUCTS.filter(p => ids.includes(p.id)).map(p => ({ ...p, ...patch }));
      const saved = await directBulkSave(changed, Object.keys(patch));
      toast(`Обновлено товаров: ${saved.length} ✅`);
    } else {
      const r = await api('/api/warehouse/products/bulk', {
        method: 'POST',
        body: JSON.stringify({ ids: [...selected].map(Number), patch }),
      });
      toast(`Обновлено товаров: ${r.updated} ✅`);
    }
    selected = new Set();
    closeBulk();
    loadList();
    loadCloudStatus();
  } catch (e) { toast(e.message, true); }
}
window.openBulkEdit = openBulkEdit;
window.applyBulk = applyBulk;

/* ---------- push-уведомления (Этап 2; нужен HTTPS) ---------- */
const PUSH_SUPPORTED = ('serviceWorker' in navigator) && ('PushManager' in window) && ('Notification' in window);

function urlB64ToUint8Array(b64) {
  const pad = '='.repeat((4 - b64.length % 4) % 4);
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return new Uint8Array([...raw].map(c => c.charCodeAt(0)));
}

async function pushRegistration() {
  if (!PUSH_SUPPORTED) return null;
  try {
    const reg = await navigator.serviceWorker.ready;
    return await reg.pushManager.getSubscription();
  } catch (e) { return null; }
}

async function enablePush() {
  if (!PUSH_SUPPORTED) {
    return toast('Push недоступен: нужен HTTPS и поддержка браузером', true);
  }
  if (Notification.permission === 'denied') {
    return toast('Уведомления запрещены в настройках браузера', true);
  }
  try {
    const settings = await api('/api/warehouse/settings');
    const vapid = settings.warehouse.vapid_public;
    if (!vapid) return toast('Ключ push ещё не создан — обновите страницу', true);
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') return toast('Разрешение не получено', true);
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8Array(vapid),
    });
    await api('/api/warehouse/push/subscribe', { method: 'POST', body: JSON.stringify({ subscription: sub.toJSON() }) });
    toast('Push-уведомления включены 🔔');
    renderPushState();
  } catch (e) { toast(e.message, true); }
}
window.enablePush = enablePush;

async function pushTest() {
  try {
    const r = await api('/api/warehouse/push/test', { method: 'POST', body: '{}' });
    toast(r.sent ? 'Тестовое уведомление отправлено 🔔' : 'Нет активных подписок (или push не работает на http)', !r.sent);
  } catch (e) { toast(e.message, true); }
}
window.pushTest = pushTest;

async function renderPushState() {
  const box = $('#push-box');
  if (!box) return;
  if (!PUSH_SUPPORTED) { box.textContent = '⚠️ Недоступно: нужен HTTPS-домен (на http превью push отключён).'; return; }
  if (Notification.permission === 'denied') { box.textContent = '⛔ Уведомления запрещены в браузере.'; return; }
  const sub = await pushRegistration();
  box.textContent = sub ? '✅ Уведомления включены для этого устройства.' : (Notification.permission === 'granted' ? 'Разрешение есть — включите уведомления.' : 'Уведомления выключены.');
}
window.renderPushState = renderPushState;

async function quickEnablePin() {
  const pin = prompt('Придумайте PIN для быстрого входа (4–8 цифр):', '');
  if (!pin) return;
  if (!/^\d{4,8}$/.test(pin)) { toast('PIN: 4–8 цифр', true); return; }
  const pin2 = prompt('Повторите PIN:', '');
  if (pin !== pin2) { toast('PIN не совпадают', true); return; }
  await quickSetup(pin);
  renderQuickStatus();
}
window.quickEnablePin = quickEnablePin;

function renderQuickStatus() {
  const el = $('#quick-status');
  if (!el) return;
  const q = (() => { try { return JSON.parse(localStorage.getItem(QUICK_KEY) || 'null'); } catch (e) { return null; } })();
  el.textContent = q
    ? (q.bio ? '✅ Вход по отпечатку' : '✅ Быстрый вход по PIN') + ' включён на этом устройстве'
    : (WEB_WEBAUTHN ? 'Быстрый вход выключен.' : 'Быстрый вход выключен. Биометрия требует HTTPS.');
}
window.renderQuickStatus = renderQuickStatus;

// обновляем состояние кнопки при открытии настроек
const _origOpenSettings = openSettings;
openSettings = async function () {
  await _origOpenSettings();
  setTimeout(renderPushState, 50);
  setTimeout(renderQuickStatus, 60);
};

/* ---------- ИИ-vision: распознавание товара по фото (Этап 3 сканер-профи) ---------- */
async function openVision() {
  $('#sheet2-title').textContent = '🤖 ИИ-vision: распознавание товара';
  $('#sheet2-body').innerHTML = `
    <p style="color:#64748b;font-size:13px;margin:0 0 12px">Сделайте фото товара — ИИ найдёт похожие карточки в каталоге склада.</p>
    <div class="card" style="align-items:center; cursor:pointer" onclick="startVisionCamera()">
      <div class="info"><div class="name">📷 Сделать фото</div><div class="meta">Камера → анализ изображения → поиск в базе</div></div>
    </div>
    <div class="card" style="align-items:center; cursor:pointer" onclick="visionFromGallery()">
      <div class="info"><div class="name">🖼 Выбрать из галереи</div><div class="meta">Загрузить готовое фото с телефона</div></div>
    </div>
    <div id="vision-results" style="margin-top:10px"></div>`;
  $('#sheet2').classList.remove('hidden');
}

async function startVisionCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    const video = document.createElement('video');
    video.srcObject = stream;
    video.autoplay = true;
    video.style.cssText = 'width:100%;max-height:300px;border-radius:12px;object-fit:cover;background:#000;';
    $('#vision-results').innerHTML = '';
    $('#vision-results').appendChild(video);
    await video.play();
    // Даём пользователю время на позиционирование
    setTimeout(async () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);
        const base64 = canvas.toDataURL('image/jpeg', 0.8).split(',')[1];
        stream.getTracks().forEach(t => t.stop());
        $('#vision-results').innerHTML = '<p style="color:#64748b;font-size:13px">🔄 Анализируем изображение…</p>';
        const result = await api('/api/warehouse/vision', {
          method: 'POST',
          body: JSON.stringify({ image: base64 }),
        });
        showVisionResults(result);
      } catch (e) {
        toast('Ошибка анализа: ' + e.message, true);
        stream.getTracks().forEach(t => t.stop());
      }
    }, 1500);
  } catch (e) {
    toast('Нет доступа к камере: ' + e.message, true);
  }
}

function visionFromGallery() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*';
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      const base64 = reader.result.split(',')[1];
      $('#vision-results').innerHTML = '<p style="color:#64748b;font-size:13px">🔄 Анализируем изображение…</p>';
      try {
        const result = await api('/api/warehouse/vision', {
          method: 'POST',
          body: JSON.stringify({ image: base64 }),
        });
        showVisionResults(result);
      } catch (err) {
        toast('Ошибка анализа: ' + err.message, true);
      }
    };
    reader.readAsDataURL(file);
  };
  input.click();
}

function showVisionResults(result) {
  const desc = result.description || 'Описание не получено';
  const matches = result.results || [];
  let html = `<div style="background:#f0fdf4;border-radius:12px;padding:10px;margin-bottom:10px;font-size:12.5px;color:#166534"><b>🤖 Описание:</b> ${esc(desc)}</div>`;
  if (matches.length === 0) {
    html += '<p style="color:#64748b">Совпадений не найдено. Попробуйте другое фото или добавьте описание товара.</p>';
  } else {
    html += `<h4 style="margin:8px 0 6px;font-size:15px">Найдено совпадений: ${matches.length}</h4>`;
    html += matches.map(m => `
      <div class="card" style="align-items:center;cursor:pointer" onclick="openForm(${m.product.id}); closeSheet2();">
        <img src="${esc(m.product.photo || '/webapp/img/products/placeholder.jpg')}" style="width:56px;height:56px;border-radius:10px;object-fit:cover;">
        <div class="info">
          <div class="name">${esc(m.product.name)}</div>
          <div class="meta">${esc(m.product.category || '')} · ${fmt(m.product.price)} · Релевантность: <b>${m.relevance}%</b></div>
        </div>
      </div>`).join('');
  }
  $('#vision-results').innerHTML = html + `<button class="btn ghost" onclick="openVision()" style="margin-top:10px">🔄 Повторить</button>`;
}

function closeSheet2() { $('#sheet2').classList.add('hidden'); }

/* ---------- Bluetooth / ТСД-сканеры (HID-режим) — Этап 3 склада ---------- */
// Bluetooth-сканеры в HID-режиме работают как клавиатура: вводят штрих-код и обычно
// шлют Enter в конце. Поддержаны оба варианта — с Enter-суффиксом и без него
// (отправка по паузе). Ввод человека отсекается по межсимвольному интервалу.
let HID_SCANNER_ACTIVE = false;
let HID_SCANNER_BUFFER = '';
let HID_LAST_CODE = '';
let HID_LAST_AT = 0;

function openHidScanMode() {
  HID_SCANNER_ACTIVE = true;
  HID_SCANNER_BUFFER = '';
  HID_LAST_CODE = '';
  HID_LAST_AT = 0;
  const modeName = { search: 'Поиск', receive: 'Приёмка', sell: 'Продажа', inventory: 'Инвентаризация' };
  $('#sheet2-title').textContent = '📶 Bluetooth / ТСД (HID)';
  $('#sheet2-body').innerHTML = `
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:12px;padding:12px;margin-bottom:12px;color:#075985;font-size:13px">
      Bluetooth-сканер в HID-режиме работает как клавиатура: подключите его к устройству
      и сканируйте — код подставится сам. Текущий режим:
      <b>${modeName[SCAN_MODE] || SCAN_MODE}</b>.
    </div>
    <button class="btn primary" id="hid-toggle" onclick="toggleHidInput()">📶 Включить HID-приём</button>
    <div class="row2" style="margin-top:10px">
      <input class="fld" id="hid-manual" inputmode="none" autocomplete="off"
             placeholder="Сюда попадёт код со сканера (или введите вручную)"
             onkeydown="if(event.key==='Enter'){event.preventDefault();const v=this.value.trim();this.value='';if(v)handleScanCode(v);}">
    </div>
    <div class="row2" style="margin-top:8px">
      <label style="font-size:12px;color:#475569;display:flex;align-items:center;gap:6px">
        <input type="checkbox" id="hid-suffix" checked> Сканер шлёт Enter в конце
      </label>
    </div>
    <div id="hid-status" style="margin-top:8px;color:#64748b;font-size:12px"></div>
    <div id="hid-log" style="margin-top:10px;max-height:160px;overflow:auto;font-size:12px"></div>`;
  $('#sheet2').classList.remove('hidden');
  activateHidInput();
}

function activateHidInput() {
  HID_SCANNER_ACTIVE = true;
  HID_SCANNER_BUFFER = '';
  const b = $('#hid-toggle');
  if (b) { b.textContent = '⏸ Выключить HID-приём'; b.classList.remove('primary'); b.classList.add('ghost'); }
  const s = $('#hid-status');
  if (s) s.innerHTML = '<b style="color:#15803d">✅ HID-приём включён</b> — сканируйте штрих-код.';
  setTimeout(() => { const i = $('#hid-manual'); if (i) i.focus(); }, 200);
}

function deactivateHidInput() {
  HID_SCANNER_ACTIVE = false;
  HID_SCANNER_BUFFER = '';
  const b = $('#hid-toggle');
  if (b) { b.textContent = '📶 Включить HID-приём'; b.classList.add('primary'); b.classList.remove('ghost'); }
  const s = $('#hid-status');
  if (s) s.textContent = 'HID-приём отключён.';
}

function toggleHidInput() {
  if (HID_SCANNER_ACTIVE) deactivateHidInput(); else activateHidInput();
}

function hidLog(code, ok) {
  const el = $('#hid-log');
  if (!el) return;
  const t = new Date().toLocaleTimeString('ru-RU');
  el.insertAdjacentHTML('afterbegin',
    `<div style="padding:5px 8px;border-radius:7px;margin-bottom:4px;background:${ok ? '#f0fdf4' : '#fef2f2'};color:${ok ? '#166534' : '#991b1b'}">
       <b>${code}</b> <span style="opacity:.7">· ${t}</span></div>`);
}

// Перехват клавиатурного ввода для HID-сканера (Bluetooth/ТСД в режиме клавиатуры).
//
// Сканер печатает символы гораздо быстрее человека, поэтому код отделяется от
// ручного ввода по межсимвольному интервалу. Раньше здесь были ошибки:
// обе ветки проверки скорости делали одно и то же (клавиатурный ввод человека
// тоже копился в буфер), при отсутствии Enter буфер не сбрасывался и коды
// склеивались, а повторный скан того же кода срабатывал дважды.
(function initHidKeyboard() {
  let lastKeyTime = 0;
  let flushTimer = null;

  const FAST_MS = 35;      // не больше этого между символами — значит, сканер
  const IDLE_FLUSH = 120;  // тишина после серии — код закончился (сканер без Enter)
  const MIN_LEN = 4;       // короче — шум
  const DEDUP_MS = 700;    // защита от дребезга/повторной отправки

  function submit(code) {
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
    HID_SCANNER_BUFFER = '';
    if (!code || code.length < MIN_LEN) return;
    const now = Date.now();
    if (code === HID_LAST_CODE && now - HID_LAST_AT < DEDUP_MS) return;
    HID_LAST_CODE = code; HID_LAST_AT = now;
    const inp = $('#hid-manual');
    if (inp) inp.value = code;
    hidLog(code, true);
    handleScanCode(code);
  }

  document.addEventListener('keydown', function(e) {
    if (!HID_SCANNER_ACTIVE) return;
    if (e.ctrlKey || e.altKey || e.metaKey) return;

    const now = Date.now();
    const delta = now - lastKeyTime;
    lastKeyTime = now;

    if (e.key === 'Enter') {
      const code = HID_SCANNER_BUFFER.trim();
      if (code) { e.preventDefault(); submit(code); }
      return;
    }
    if (e.key.length !== 1) return;   // Shift, стрелки, F-клавиши и т.п.

    // Пауза между символами слишком велика — это человек, начинаем буфер заново.
    if (delta > FAST_MS) HID_SCANNER_BUFFER = '';
    HID_SCANNER_BUFFER += e.key;

    // Сканеры без Enter-суффикса: отправляем по паузе.
    if (flushTimer) clearTimeout(flushTimer);
    flushTimer = setTimeout(() => {
      const noSuffix = $('#hid-suffix') && !$('#hid-suffix').checked;
      const code = HID_SCANNER_BUFFER.trim();
      if (noSuffix && code.length >= MIN_LEN) submit(code);
      else HID_SCANNER_BUFFER = '';   // иначе просто чистим, чтобы коды не склеивались
    }, IDLE_FLUSH);
  });
})();

function closeSheet2() { $('#sheet2').classList.add('hidden'); }

/* ---------- инвентаризация со сверкой (Этап 3 склада) ---------- */
async function openInventoryCompare() {
  // Простая версия: сравниваем текущий список товаров с введёнными остатками
  $('#sheet2-title').textContent = '🧮 Инвентаризация: сверка';
  $('#sheet2-body').innerHTML = `
    <p style="color:#64748b;font-size:12px;margin:0 0 10px">Выберите несколько товаров (чекбоксами в списке), затем нажмите «Сверить» — система сравнит фактические остатки с базой.</p>
    <button class="btn primary" onclick="runInventoryCompare()">✅ Сверить остатки выбранных</button>
    <div id="inv-compare-results" style="margin-top:10px"></div>`;
  $('#sheet2').classList.remove('hidden');
}

async function runInventoryCompare() {
  const ids = [...selected].map(Number);
  if (!ids.length) {
    toast('Отметьте товары чекбоксами для сверки', true);
    return;
  }
  // Для демонстрации: сравниваем с текущими остатками (как если бы фактический = текущий — идеальный случай)
  // В реальном использовании — пользователь вводит фактические остатки
  const items = ids.map(id => {
    const p = PRODUCTS.find(x => x.id === id);
    return { product_id: id, qty: p ? p.stock : 0 };
  });
  try {
    const result = await api('/api/warehouse/inventory/compare', {
      method: 'POST',
      body: JSON.stringify({ items }),
    });
    renderInventoryResults(result);
  } catch (e) {
    toast('Ошибка сверки: ' + e.message, true);
  }
}

function renderInventoryResults(result) {
  const summary = result.summary || {};
  const results = result.results || {};
  const discrepancies = results.discrepancies || [];
  const matches = results.matches || [];
  const missing = results.missing_in_db || [];
  let html = `<div style="background:#f8fafc;border-radius:12px;padding:12px;margin-bottom:8px;font-size:13px;color:#334155">
    <b>📊 Итоги сверки:</b><br>
    Проверено позиций: <b>${summary.total_items_checked || 0}</b> ·
    Совпадений: <b style="color:#15803d">${summary.matches || 0}</b> ·
    Расхождений: <b style="color:#b45309">${summary.discrepancies || 0}</b> ·
    В БД всего: <b>${summary.total_db_items || 0}</b>
  </div>`;
  if (discrepancies.length > 0) {
    html += `<h4 style="margin:8px 0 4px;color:#b45309">⚠️ Расхождения (${discrepancies.length})</h4>`;
    html += discrepancies.map(d => `
      <div class="card" style="border-left:3px solid #b45309">
        <div class="info">
          <div class="name">${esc(d.product_name || '—')}</div>
          <div class="meta">ID: ${d.product_id} · Категория: ${esc(d.category || '')}<br>
          Фактический остаток: <b>${d.qty_actual}</b> · В базе: <b>${d.qty_db}</b> · Разница: <b>${d.diff > 0 ? '+' : ''}${d.diff}</b> (${d.status === 'surplus' ? 'излишек' : 'недостача'})</div>
        </div>
      </div>`).join('');
  } else if (matches.length > 0) {
    html += `<p style="color:#15803d;font-weight:600">✅ Все проверенные остатки совпадают с базой!</p>`;
  }
  if (missing.length > 0) {
    html += `<h4 style="margin:8px 0 4px;color:#dc2626">❌ Не найдены в базе (${missing.length})</h4>`;
    html += `<div style="font-size:12px;color:#64748b;margin-bottom:8px">Товары отсутствуют в каталоге склада — проверьте, не удалены ли они или не добавлены под другим ID.</div>`;
  }
  $('#inv-compare-results').innerHTML = html + `<button class="btn ghost" onclick="openInventoryCompare()" style="margin-top:8px">🔄 Повторить сверку</button>`;
}

function closeSheet2() { $('#sheet2').classList.add('hidden'); }

// Скачивание защищённого файла: window.open не умеет слать X-Wh-Token,
// поэтому тянем через fetch с заголовками и отдаём как blob.
async function downloadAuthed(url, filename, openInNewTab) {
  const res = await fetch(url, { headers: { 'X-Wh-Token': TOKEN, 'X-Admin-Token': TOKEN } });
  if (!res.ok) {
    let msg = 'Ошибка ' + res.status;
    try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (e) {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  if (openInNewTab) {
    const w = window.open(href, '_blank');
    if (!w) { const a = document.createElement('a'); a.href = href; a.download = filename; a.click(); }
  } else {
    const a = document.createElement('a');
    a.href = href; a.download = filename; a.click();
  }
  setTimeout(() => URL.revokeObjectURL(href), 60000);
}

async function printByFilter() {
  const cat = $('#pf-cat').value.trim();
  const loc = $('#pf-loc').value.trim();
  if (!cat && !loc) return toast('Укажите категорию или место для фильтра', true);
  try {
    await downloadAuthed(
      `/api/warehouse/labels.pdf?cat=${encodeURIComponent(cat)}&loc=${encodeURIComponent(loc)}`,
      'labels.pdf', true);
    toast('Этикетки по фильтру готовы 🖨');
    closeSheet2();
  } catch (e) { toast(e.message, true); }
}

// Ценники для торгового зала (Этап 4): по выделенным товарам или по фильтру.
async function printPriceTags() {
  const ids = [...selected];
  const cat = ($('#pf-cat') && $('#pf-cat').value.trim()) || '';
  const loc = ($('#pf-loc') && $('#pf-loc').value.trim()) || '';
  if (!ids.length && !cat && !loc) {
    return toast('Отметьте товары чекбоксами или задайте фильтр', true);
  }
  const q = ids.length
    ? `ids=${ids.join(',')}`
    : `cat=${encodeURIComponent(cat)}&loc=${encodeURIComponent(loc)}`;
  try {
    await downloadAuthed(`/api/warehouse/price-tags.pdf?${q}`, 'price-tags.pdf', true);
    toast('Ценники готовы 🏷');
    closeSheet2();
  } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------ настройки
async function manageWarehouses() { if (!(WHOAMI && WHOAMI.role === 'admin')) return toast('Только администратор', true); const name=prompt('Название нового склада'); if(name){await api('/api/warehouse/warehouses',{method:'POST',body:JSON.stringify({name})}); await loadWarehouses(); toast('Склад создан');} else alert('Склады:\n'+WAREHOUSES.map(w=>w.id+': '+w.name).join('\n')); }
async function renameWarehouse(id){const v=prompt('Новое название', WAREHOUSES.find(w=>w.id===id)?.name||''); if(!v)return; await api('/api/warehouse/warehouses/'+id,{method:'PUT',body:JSON.stringify({name:v})}); await loadWarehouses(); toast('Склад переименован');}
async function removeWarehouse(id){if(!confirm('Удалить склад?'))return; await api('/api/warehouse/warehouses/'+id,{method:'DELETE'}); await loadWarehouses(); toast('Склад удалён');}
window.manageWarehouses=manageWarehouses; window.renameWarehouse=renameWarehouse; window.removeWarehouse=removeWarehouse;
async function openSettings() {
  try {
    const s = await ensureWarehouseSettings(true);
    const isAdmin = WHOAMI && WHOAMI.role === 'admin';
    const dbMode = normalizeDbMode(s.cloud.db_mode, s.cloud.provider);
    const keyVal = s.cloud.key === '•••' ? '' : (s.cloud.key || '');
    const publicKeyVal = s.cloud.public_key === '•••' ? '' : (s.cloud.public_key || '');
    const apkVersion = getNativeAppVersion();
    const apkServer = getNativeServerUrl();
    const apkBlock = canOpenNativeAppSettings() ? `
      <h3 style="margin:0 0 8px">📱 APK: подключение к складу</h3>
      <p style="color:#64748b;font-size:12px;margin:0 0 8px">Адрес сервера хранится в самом Android-приложении. Если вы перенесёте склад на другой VPS или домен, меняйте адрес здесь — пересобирать APK не нужно.</p>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;padding:10px 12px;margin-bottom:8px;color:#1d4ed8;font-size:12px">Текущий адрес: <b>${esc(apkServer || 'не задан')}</b>${apkVersion ? ` · APK ${esc(apkVersion)}` : ''}</div>
      <div class="airow">
        <button class="mini" onclick="openNativeAppSettings()">⚙️ Настроить адрес APK</button>
        <button class="mini" onclick="copyNativeServerUrl()">📋 Скопировать адрес</button>
      </div>
    ` : '';
    $('#sheet2-title').textContent = '⚙️ Настройки';
    $('#sheet2-body').innerHTML = (isAdmin ? `<h3>🏬 Склады</h3><button class=\"mini\" onclick=\"manageWarehouses()\">Управление складами</button>` : '') + apkBlock + `
      <h3 style="margin:14px 0 8px">🗄 База товаров: 4 режима подключения</h3>
      <p style="color:#64748b;font-size:12px;margin:0 0 8px">Можно выбрать: <b>VPS</b>, <b>VPS → Supabase</b> или <b>Direct Supabase</b>. Во всех режимах фото, картинки и backup ниже остаются в Yandex Object Storage.</p>
      <label class="lb" style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="cl-en" ${s.cloud.enabled ? 'checked' : ''} ${isAdmin ? '' : 'disabled'} style="accent-color:#0f766e"> Включить внешнюю синхронизацию / гибридную БД</label>
      <select class="fld" id="cl-db-mode" ${isAdmin ? '' : 'disabled'}>
        <option value="vps" ${dbMode === 'vps' ? 'selected' : ''}>VPS / SQLite — живая база на сервере</option>
        <option value="supabase_proxy" ${dbMode === 'supabase_proxy' ? 'selected' : ''}>VPS → Supabase — backend работает с Supabase</option>
        <option value="supabase_direct" ${dbMode === 'supabase_direct' ? 'selected' : ''}>Direct Supabase — приложение работает с Supabase напрямую</option>
        <option value="mysql" ${dbMode === 'mysql' ? 'selected' : ''}>MySQL / MariaDB VPS — управление через phpMyAdmin</option>
      </select>
      <div id="db-vps-note" style="${dbMode === 'vps' ? '' : 'display:none'};background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;padding:10px 12px;margin:0 0 10px;color:#1d4ed8;font-size:12px">Живая база склада остаётся в <code>data/shop.db</code> на VPS. APK подключается только к вашему серверу, а каталог/фото/backup можно синхронизировать отдельно.</div>
      <div id="db-proxy-note" style="${dbMode === 'supabase_proxy' ? '' : 'display:none'};background:#ecfeff;border:1px solid #a5f3fc;border-radius:12px;padding:10px 12px;margin:0 0 10px;color:#0f766e;font-size:12px">Гибридный режим: APK входит через VPS, а backend читает и пишет каталог в Supabase. Это самый безопасный вариант для совместной работы.</div>
      <div id="db-direct-note" style="${dbMode === 'supabase_direct' ? '' : 'display:none'};background:#fff7ed;border:1px solid #fdba74;border-radius:12px;padding:10px 12px;margin:0 0 10px;color:#c2410c;font-size:12px">Direct-режим: после обычного входа через VPS приложение читает и пишет каталог напрямую в Supabase по public key. VPS при этом зеркалирует изменения в локальную SQLite для витрины, заказов и служебных API.</div>
      <div id="mysql-fields" style="${dbMode === 'mysql' ? '' : 'display:none'}"><input class="fld" id="mysql-host" placeholder="MySQL host" value="${esc(s.cloud.mysql_host || '')}" ${isAdmin ? '' : 'disabled'}><div class="row2"><input class="fld" id="mysql-port" type="number" value="${s.cloud.mysql_port || 3306}" placeholder="Порт"><input class="fld" id="mysql-user" placeholder="Пользователь" value="${esc(s.cloud.mysql_user || '')}"></div><div class="row2"><input class="fld" id="mysql-db" placeholder="База данных" value="${esc(s.cloud.mysql_database || 'shop')}"><input class="fld" id="mysql-table" placeholder="Таблица каталога" value="${esc(s.cloud.mysql_table || 'products')}"></div><input class="fld" id="mysql-pass" type="password" placeholder="Пароль (пусто = не менять)"></div>
      <div id="sb-fields" style="${dbMode === 'supabase_proxy' || dbMode === 'supabase_direct' ? '' : 'display:none'}">
        <input class="fld" id="cl-url" placeholder="Supabase URL, например https://xxxx.supabase.co" value="${esc(s.cloud.url)}" ${isAdmin ? '' : 'disabled'}>
        <input class="fld" id="cl-key" type="password" placeholder="Server key для VPS → Supabase (service role или ключ с правами на products)" value="${esc(keyVal)}" ${isAdmin ? '' : 'disabled'}>
        <input class="fld" id="sb-public-key" type="password" placeholder="Direct public/anon key для APK/Web → Supabase (нужен только для Direct режима)" value="${esc(publicKeyVal)}" ${isAdmin ? '' : 'disabled'}>
        <div class="row2">
          <input class="fld" id="sb-schema" placeholder="Schema" value="${esc(s.cloud.supabase_schema || 'public')}" ${isAdmin ? '' : 'disabled'}>
          <input class="fld" id="sb-table" placeholder="Table / View" value="${esc(s.cloud.supabase_table || 'products')}" ${isAdmin ? '' : 'disabled'}>
        </div>
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:10px 12px;margin:0 0 10px;color:#475569;font-size:12px">В режиме <b>VPS → Supabase</b> используется server key на VPS. В режиме <b>Direct Supabase</b> приложение получает только public/anon key после warehouse-login на VPS, а сервисный ключ остаётся на сервере.</div>
      </div>

      <h3 style="margin:14px 0 8px">☁️ Фото, картинки и backup</h3>
      <select class="fld" id="photo-provider" ${isAdmin ? "" : "disabled"}><option value="s3" ${(s.cloud.photo_provider || "s3") === "s3" ? "selected" : ""}>S3: Yandex / VK / другое</option><option value="yandex_disk" ${s.cloud.photo_provider === "yandex_disk" ? "selected" : ""}>Yandex Disk API (заглушка)</option></select>
      <input class="fld" id="yd-token" type="password" placeholder="Yandex Disk OAuth token (вставьте самостоятельно)" ${isAdmin ? "" : "disabled"}>
      <input class="fld" id="yd-path" placeholder="Путь на Диске" value="${esc(s.cloud.yandex_disk_path || "app:/shop-photos/products")}" ${isAdmin ? "" : "disabled"}>
      <p style="color:#64748b;font-size:12px;margin:0 0 8px">Эти поля используются для всех трёх режимов базы. Рекомендуемая схема: <b>shop-photos</b> для фото и <b>shop-backups</b> для резервных копий SQLite.</p>
      <div id="s3-fields">
        <select class="fld" id="s3-preset" ${isAdmin ? '' : 'disabled'}>
          <option value="selectel">Selectel — Объектное хранилище</option>
          <option value="cloudru">Cloud.ru — Object Storage</option>
          <option value="vk">VK Cloud — Объектное хранилище</option>
          <option value="yandex">Яндекс — Объектное хранилище</option>
          <option value="minio">MinIO (свой сервер)</option>
          <option value="custom">Другой S3-совместимый</option>
        </select>
        <div id="s3-hint" style="color:#64748b;font-size:11.5px;margin:2px 2px 8px"></div>
        <input class="fld" id="s3-ep" placeholder="Endpoint (пусто = из пресета)" value="${esc(s.cloud.s3_endpoint || '')}" ${isAdmin ? '' : 'disabled'}>
        <input class="fld" id="s3-ak" placeholder="Access Key" value="${esc(s.cloud.s3_access_key || '')}" ${isAdmin ? '' : 'disabled'}>
        <input class="fld" id="s3-sk" type="password" placeholder="Secret Key (пусто = не менять)" ${isAdmin ? '' : 'disabled'}>
        <div class="row2">
          <input class="fld" id="s3-bucket" placeholder="Bucket для фото" value="${esc(s.cloud.bucket || 'shop-photos')}" ${isAdmin ? '' : 'disabled'}>
          <input class="fld" id="s3-region" placeholder="Регион (пусто = из пресета)" value="${esc(s.cloud.s3_region || '')}" ${isAdmin ? '' : 'disabled'}>
        </div>
        <div class="row2">
          <input class="fld" id="s3-photo-prefix" placeholder="Папка/префикс для фото" value="${esc(s.cloud.photo_prefix || 'products')}" ${isAdmin ? '' : 'disabled'}>
          <input class="fld" id="s3-backup-bucket" placeholder="Bucket для backup SQLite" value="${esc(s.cloud.backup_bucket || 'shop-backups')}" ${isAdmin ? '' : 'disabled'}>
        </div>
        <div class="row2">
          <input class="fld" id="s3-catalog-prefix" placeholder="Папка/префикс для catalog JSON" value="${esc(s.cloud.catalog_prefix || 'catalog')}" ${isAdmin ? '' : 'disabled'}>
          <input class="fld" id="s3-backup-prefix" placeholder="Папка/префикс для backup SQLite" value="${esc(s.cloud.backup_prefix || 'sqlite')}" ${isAdmin ? '' : 'disabled'}>
        </div>
      </div>
      <label class="lb" style="display:flex;gap:8px;align-items:center;margin-top:6px">
        <input type="checkbox" id="cl-cdn" ${s.cloud.use_cdn ? 'checked' : ''} ${isAdmin ? '' : 'disabled'} style="accent-color:#0f766e">
        Подтягивать фото с облака (CDN-URL, быстрее загрузка)
      </label>
      <label class="lb" style="display:flex;gap:8px;align-items:center">
        <input type="checkbox" id="cl-autosync" ${s.warehouse.auto_sync_cloud ? 'checked' : ''} ${isAdmin ? '' : 'disabled'} style="accent-color:#0f766e">
        Автосинхронизация фото при сохранении товара
      </label>
      <div id="cloud-status" style="color:#64748b;font-size:12px;margin:4px 0 8px"></div>
      ${isAdmin ? `
      <div class="airow">
        <button class="mini" onclick="cloudTest()">🔌 Проверить</button>
        <button class="mini" onclick="cloudSync()">🔄 Синхронизировать</button>
        <button class="mini" onclick="cloudBackup()">🗄 Бэкап БД</button>
        <button class="mini" onclick="cloudPull()">⬇️ Из облака</button>
      </div>
      <div class="hint" id="cloud-note" style="color:#64748b;font-size:12px;margin-bottom:8px"></div>` : ''}

      <h3 style="margin:14px 0 8px">🔓 Быстрый вход (PIN / отпечаток)</h3>
      <p style="color:#64748b;font-size:12px;margin:0 0 8px">Вход без пароля: PIN на этом устройстве или биометрия (отпечаток/лицо) через WebAuthn. Отключается при смене пароля.</p>
      <div class="row2" style="margin-bottom:8px">
        <button class="mini" onclick="quickEnablePin()">🔢 Включить PIN</button>
        <button class="mini" onclick="quickDisable()">Отключить</button>
        <button class="mini" onclick="bioSetup()">👆 Включить отпечаток</button>
      </div>
      <div id="quick-status" style="color:#64748b;font-size:12px;margin:0 0 8px"></div>

      <h3 style="margin:14px 0 8px">🔔 Push-уведомления</h3>
      <p style="color:#64748b;font-size:12px;margin:0 0 8px">Уведомления о новых заказах и оплатах прямо на телефон. Требуют HTTPS-домен (на http превью недоступны).</p>
      <div id="push-box" style="color:#64748b;font-size:12px;margin:0 0 8px"></div>
      <div class="row2">
        <button class="mini" onclick="enablePush()" id="push-en-btn">🔔 Включить уведомления</button>
        <button class="mini" onclick="pushTest()">Тестовое</button>
      </div>

      <h3 style="margin:14px 0 8px">📣 Публикация в соцсети</h3>
      <label class="lb" style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="pub-auto" ${s.social.auto_post_new ? 'checked' : ''} ${isAdmin ? '' : 'disabled'} style="accent-color:#0f766e"> Автопубликация новых товаров</label>
      <input class="fld" id="pub-tg" placeholder="Telegram-канал (@channel или -100…)" value="${esc(s.social.telegram_channel)}" ${isAdmin ? '' : 'disabled'}>
      <input class="fld" id="pub-vk" placeholder="VK: ID группы" value="${esc(s.social.vk_group_id)}" ${isAdmin ? '' : 'disabled'}>
      <input class="fld" id="pub-ig" placeholder="Instagram: business user_id (для Graph API)" value="${esc(s.social.instagram_user_id || '')}" ${isAdmin ? '' : 'disabled'}>
      <input class="fld" id="pub-igt" type="password" placeholder="Instagram: long-lived token (пусто = не менять)" ${isAdmin ? '' : 'disabled'}>
      <p style="color:#64748b;font-size:12px;margin:0 0 8px">VK-токен и Avito-ключи — в админ-панели сайта. Кнопка 📣 публикует в Telegram, VK и Instagram (если токен задан; иначе Instagram отдаёт готовый текст+фото для ручной публикации).</p>

      <h3 style="margin:14px 0 8px">⏰ Отложенные публикации (ТЗ SM-3)</h3>
      <p style="color:#64748b;font-size:12px;margin:0 0 8px">Запланируйте пост товара на дату — бот опубликует его автоматически в выбранную площадку.</p>
      <select class="fld" id="sp-product"></select>
      <div class="row2">
        <select class="fld" id="sp-platform">
          <option value="telegram">Telegram</option>
          <option value="vk">VK</option>
          <option value="instagram">Instagram</option>
          <option value="avito">Avito</option>
        </select>
        <input class="fld" id="sp-when" type="datetime-local">
      </div>
      <button class="btn primary" onclick="schedulePost()">Запланировать</button>
      <div id="sp-list" style="margin-top:10px"></div>
      <h3 style="margin:14px 0 8px">🖨 Принтеры наклеек</h3>
      <div id="pr-list"></div>
      ${isAdmin ? `<button class="mini" onclick="addPrinter()">＋ Добавить принтер</button>` : ''}

      <h3 style="margin:14px 0 8px">🔑 Аккаунт</h3>
      <div class="row2">
        <input class="fld" id="pw-old" type="password" placeholder="Текущий пароль">
        <input class="fld" id="pw-new" type="password" placeholder="Новый пароль">
      </div>
      <button class="btn ghost" onclick="changePassword()">Сменить пароль</button>

      ${isAdmin ? `<button class="btn primary" style="margin-top:14px" onclick="saveSettings()">💾 Сохранить настройки</button>` : ''}
    `;
    renderPrinterList(s.printers);
    $('#cl-db-mode').addEventListener('change', e => {
      const v = e.target.value;
      $('#sb-fields').style.display = (v === 'supabase_proxy' || v === 'supabase_direct') ? '' : 'none';
      $('#mysql-fields').style.display = v === 'mysql' ? '' : 'none';
      $('#db-vps-note').style.display = v === 'vps' ? '' : 'none';
      $('#db-proxy-note').style.display = v === 'supabase_proxy' ? '' : 'none';
      $('#db-direct-note').style.display = v === 'supabase_direct' ? '' : 'none';
    });
    $('#s3-preset').value = s.cloud.s3_preset || 'yandex';
    $('#s3-preset').addEventListener('change', e => applyS3Preset(e.target.value, true));
    loadPresets().then(() => {
      const cur = $('#s3-preset').value;
      // endpoint подставляем, только если он не задан вручную
      const preset = S3PRESETS[cur];
      if (preset && !($('#s3-ep').value.trim())) $('#s3-ep').value = preset.endpoint;
      if (preset && !($('#s3-region').value.trim())) $('#s3-region').value = preset.region;
      applyS3Preset(cur);
    });
    loadCloudStatus();
    renderApkSettingsBox();
    $('#sheet2').classList.remove('hidden');
  } catch (e) { toast(e.message, true); }
}

let S3PRESETS = {};
async function loadPresets() {
  try { S3PRESETS = (await api('/api/warehouse/cloud/presets')).reduce((m, p) => { m[p.id] = p; return m; }, {}); }
  catch (e) { S3PRESETS = {}; }
}

function applyS3Preset(id, fill) {
  const p = S3PRESETS[id];
  if (!p) return;
  $('#s3-ep').placeholder = p.endpoint || 'Endpoint (свой)';
  $('#s3-region').placeholder = p.region || 'Регион';
  $('#s3-hint').textContent = '🔑 ' + p.hint;
  if (fill) {
    $('#s3-ep').value = p.endpoint || '';
    $('#s3-region').value = p.region || '';
  }
}

async function loadCloudStatus() {
  try {
    const st = await api('/api/warehouse/cloud/status');
    const backup = st.backup || {};
    const dbLabel = dbModeLabel(st.db_mode);
    const storageLabel = (st.storage_preset || 's3').toUpperCase();
    $('#cloud-status').textContent = st.enabled
      ? `🗄 БД: ${dbLabel} · ☁️ storage: ${storageLabel} · CDN: ${st.use_cdn ? 'вкл' : 'выкл'} · фото в облаке: ${st.photos_synced}` +
        (st.last_sync ? ` · синхронизировано ${new Date(st.last_sync).toLocaleString('ru-RU')}` : ' · ещё не синхронизировали') +
        (backup.at ? ` · backup SQLite: ${backup.bucket}/${backup.key}` : '')
      : '☁️ внешняя синхронизация выключена — живая база остаётся на VPS';
  } catch (e) { $('#cloud-status').textContent = ''; }
}

async function cloudPull() {
  if (!confirm('Восстановить каталог из облака? Локальные товары будут обновлены данными облака.')) return;
  $('#cloud-note').textContent = 'Загружаем из облака…';
  try {
    const r = await api('/api/warehouse/cloud/pull', { method: 'POST', body: '{}' });
    $('#cloud-note').textContent = r.ok
      ? `✅ Восстановлено: создано ${r.created}, обновлено ${r.updated}`
      : '❌ ' + (r.error || 'ошибка');
    loadList();
    loadCloudStatus();
  } catch (e) { $('#cloud-note').textContent = '❌ ' + e.message; }
}

let PRINTERS = [];
function renderPrinterList(list) {
  PRINTERS = JSON.parse(JSON.stringify(list || []));
  $('#pr-list').innerHTML = PRINTERS.map((p, i) => `
    <div class="card" style="align-items:center">
      <div class="info">
        <input class="fld" data-i="${i}" data-f="name" value="${esc(p.name)}" style="margin:0 0 6px">
        <div class="row2" style="gap:6px">
          <input class="fld" data-i="${i}" data-f="width_mm" type="number" value="${p.width_mm}" placeholder="Ш, мм" style="margin:0">
          <input class="fld" data-i="${i}" data-f="height_mm" type="number" value="${p.height_mm}" placeholder="В, мм" style="margin:0">
          <select class="fld" data-i="${i}" data-f="format" style="margin:0">
            <option value="pdf" ${p.format === 'pdf' ? 'selected' : ''}>PDF</option>
            <option value="zpl" ${p.format === 'zpl' ? 'selected' : ''}>ZPL</option>
            <option value="epl" ${p.format === 'epl' ? 'selected' : ''}>EPL</option>
          </select>
          <input class="fld" data-i="${i}" data-f="copies" type="number" value="${p.copies || 1}" placeholder="Копий" style="margin:0;max-width:64px">
          <input class="fld" data-i="${i}" data-f="host" value="${esc(p.host || "")}" placeholder="IP принтера" style="margin:0">
          <input class="fld" data-i="${i}" data-f="port" type="number" value="${p.port || 9100}" placeholder="Порт" style="margin:0;max-width:75px">
        </div>
      </div>
      <button class="mini danger" onclick="delPrinter(${i})">✕</button>
    </div>`).join('') || '<p style="color:#64748b;font-size:13px">Принтеров нет</p>';
  document.querySelectorAll('#pr-list [data-i]').forEach(el => el.addEventListener('change', () => {
    PRINTERS[+el.dataset.i][el.dataset.f] = el.type === 'number' ? (+el.value || 0) : el.value;
  }));
}

function addPrinter() {
  PRINTERS.push({ name: 'Новый принтер', width_mm: 58, height_mm: 40, format: 'zpl', copies: 1, host: '', port: 9100 });
  renderPrinterList(PRINTERS);
}

function delPrinter(i) { PRINTERS.splice(i, 1); renderPrinterList(PRINTERS); }

async function saveSettings() {
  try {
    await api('/api/warehouse/settings', { method: 'PUT', body: JSON.stringify({
      cloud: { enabled: $('#cl-en').checked, provider: 's3', db_mode: $('#cl-db-mode').value,
               use_cdn: $('#cl-cdn').checked,
               url: $('#cl-url').value.trim(), key: $('#cl-key').value.trim(), public_key: $('#sb-public-key').value.trim(),
               supabase_schema: $('#sb-schema').value.trim() || 'public',
               supabase_table: $('#sb-table').value.trim() || 'products',
               bucket: $('#s3-bucket').value.trim() || 'shop-photos',
               photo_prefix: $('#s3-photo-prefix').value.trim() || 'products',
               catalog_prefix: $('#s3-catalog-prefix').value.trim() || 'catalog',
               backup_bucket: $('#s3-backup-bucket').value.trim() || 'shop-backups',
               backup_prefix: $('#s3-backup-prefix').value.trim() || 'sqlite',
               s3_preset: $('#s3-preset').value, s3_endpoint: $('#s3-ep').value.trim(),
               s3_access_key: $('#s3-ak').value.trim(),
               s3_secret_key: $('#s3-sk').value.trim(), photo_provider: $('#photo-provider').value, yandex_disk_token: $('#yd-token').value.trim() || s.cloud.yandex_disk_token || '', yandex_disk_path: $('#yd-path').value.trim() || 'app:/shop-photos/products', s3_region: $('#s3-region').value.trim(),
               mysql_host: $('#mysql-host')?.value.trim() || s.cloud.mysql_host || '', mysql_port: +($('#mysql-port')?.value || 3306), mysql_user: $('#mysql-user')?.value.trim() || s.cloud.mysql_user || '', mysql_database: $('#mysql-db')?.value.trim() || 'shop', mysql_table: $('#mysql-table')?.value.trim() || 'products', mysql_password: $('#mysql-pass')?.value || '•••' },
      warehouse: { auto_sync_cloud: $('#cl-autosync').checked },
      printers: PRINTERS,
      social: { auto_post_new: $('#pub-auto').checked, telegram_channel: $('#pub-tg').value.trim(),
                vk_group_id: $('#pub-vk').value.trim(),
                instagram_user_id: $('#pub-ig').value.trim(), instagram_token: $('#pub-igt').value.trim() },
    }) });
    WAREHOUSE_SETTINGS = null;
    DIRECT_CFG = null;
    toast('Настройки сохранены ✅');
    closeSheet2();
    loadList();
    loadCloudStatus();
  } catch (e) { toast(e.message, true); }
}

async function cloudTest() {
  $('#cloud-note').textContent = 'Проверяем подключение к БД и Object Storage…';
  try {
    const r = await api('/api/warehouse/cloud/test', { method: 'POST', body: '{}' });
    const storage = r.storage || {};
    const database = r.database || {};
    const parts = [
      `БД ${String(database.mode || 'vps').toUpperCase()}: ${database.ok ? 'OK' : 'ERROR'}`,
      `Object Storage: ${storage.ok ? 'OK' : 'ERROR'}`
    ];
    if (database.mode === 'supabase_direct' && database.direct_public) {
      parts.push(`Direct key: ${database.direct_public.ok ? 'OK' : 'ERROR'}`);
    }
    $('#cloud-note').textContent = (r.ok ? '✅ ' : '⚠️ ') + parts.join(' · ')
      + (!r.ok && (database.error || (database.direct_public || {}).error || storage.error) ? ` · ${database.error || (database.direct_public || {}).error || storage.error}` : '');
  } catch (e) { $('#cloud-note').textContent = '❌ ' + e.message; }
}

async function cloudSync() {
  $('#cloud-note').textContent = 'Синхронизируем (товары + фото)…';
  try {
    const r = await api('/api/warehouse/cloud/sync', { method: 'POST', body: '{}' });
    $('#cloud-note').textContent = r.ok
      ? `✅ Загружено: ${r.products} товаров, ${r.photos.uploaded} фото`
      : '❌ ' + (r.error || 'ошибка');
    loadCloudStatus();
  } catch (e) { $('#cloud-note').textContent = '❌ ' + e.message; }
}

async function cloudBackup() {
  $('#cloud-note').textContent = 'Создаём backup SQLite и отправляем в облако…';
  try {
    const r = await api('/api/warehouse/cloud/backup', { method: 'POST', body: '{}' });
    $('#cloud-note').textContent = r.ok
      ? `✅ Backup загружен: ${r.bucket}/${r.key}`
      : '❌ ' + (r.error || 'ошибка');
    loadCloudStatus();
  } catch (e) { $('#cloud-note').textContent = '❌ ' + e.message; }
}

async function changePassword() {
  try {
    await api('/api/warehouse/me/password', { method: 'POST', body: JSON.stringify({
      old_password: $('#pw-old').value, new_password: $('#pw-new').value }) });
    toast('Пароль изменён ✅');
    $('#pw-old').value = ''; $('#pw-new').value = '';
  } catch (e) { toast(e.message, true); }
}

// пользователи (только админ склада)
async function openUsers() {
  try {
    const users = await api('/api/warehouse/users');
    const isAdmin = WHOAMI && WHOAMI.role === 'admin';
    $('#sheet2-title').textContent = '👥 Пользователи склада';
    $('#sheet2-body').innerHTML = `
      <p style="color:#64748b;font-size:12.5px;margin:0 0 10px">Единая база: все устройства видят одни и те же товары, фото и статусы в реальном времени.</p>
      ${users.map(u => `
        <div class="card" style="align-items:center">
          <div class="info">
            <div class="name">${esc(u.name)} ${u.role === 'admin' ? '👑' : ''}</div>
            <div class="meta">${esc(u.login)} · ${u.role === 'admin' ? 'администратор' : 'сотрудник'}</div>
          </div>
          ${isAdmin && u.login !== 'admin' ? `<button class="mini danger" onclick="delUser(${u.id})">✕</button>` : ''}
        </div>`).join('')}
      ${isAdmin ? `
        <h3 style="margin-top:14px">Добавить сотрудника</h3>
        <div class="row2"><input class="fld" id="nu-login" placeholder="Логин"><input class="fld" id="nu-name" placeholder="Имя"></div>
        <div class="row2"><input class="fld" id="nu-pass" type="password" placeholder="Пароль">
          <select class="fld" id="nu-role"><option value="worker">Сотрудник</option><option value="admin">Администратор</option></select></div>
        <button class="btn primary" onclick="addUser()">Добавить</button>` : ''}`;
    $('#sheet2').classList.remove('hidden');
  } catch (e) { toast('Только администратор склада управляет пользователями', true); }
}

async function addUser() {
  try {
    await api('/api/warehouse/users', { method: 'POST', body: JSON.stringify({
      login: $('#nu-login').value, name: $('#nu-name').value,
      password: $('#nu-pass').value, role: $('#nu-role').value }) });
    toast('Сотрудник добавлен ✅');
    openUsers();
  } catch (e) { toast(e.message, true); }
}

async function delUser(id) {
  if (!confirm('Удалить пользователя?')) return;
  try { await api('/api/warehouse/users/' + id, { method: 'DELETE' }); toast('Удалён'); openUsers(); }
  catch (e) { toast(e.message, true); }
}

async function openReports() { $('#sheet2-title').textContent='📊 Отчёты'; $('#sheet2-body').innerHTML=`<p>Выберите отчёт:</p><div class="row2">${['turnover','dead-stock','stock-value','abc'].map(k=>`<button class="mini" onclick="downloadReport('${k}')">${k}</button>`).join('')}</div><p style="color:#64748b;font-size:12px">PDF будет загружен с учётом выбранного склада.</p>`; $('#sheet2').classList.remove('hidden'); }
async function downloadReport(kind) { try { const r=await fetch('/api/warehouse/reports/'+kind+'.pdf',{headers:{'X-Wh-Token':TOKEN,'X-Admin-Token':TOKEN}}); if(!r.ok) throw new Error('Ошибка '+r.status); const a=document.createElement('a'); a.href=URL.createObjectURL(await r.blob()); a.download='warehouse-'+kind+'.pdf'; a.click(); } catch(e){toast(e.message,true);} }
window.openReports=openReports; window.downloadReport=downloadReport;
// журнал операций
async function openLog() {
  try {
    const log = await api('/api/warehouse/log');
    $('#sheet2-title').textContent = '📋 Журнал операций';
    $('#sheet2-body').innerHTML = log.length ? log.map(l => `
      <div class="card" style="align-items:center">
        <div class="info">
          <div class="name">${esc(l.user_name)} — ${esc(l.action)}</div>
          <div class="meta">${esc(l.details)} · ${new Date(l.ts).toLocaleString('ru-RU')}</div>
        </div>
      </div>`).join('') : '<p style="color:#64748b">Операций пока нет</p>';
    $('#sheet2').classList.remove('hidden');
  } catch (e) { toast(e.message, true); }
}

// тёмная тема (ТЗ 7.3)
(function () {
  if (localStorage.getItem('wh_theme') === 'dark') document.body.dataset.theme = 'dark';
})();
function toggleTheme() {
  const dark = document.body.dataset.theme !== 'dark';
  document.body.dataset.theme = dark ? 'dark' : '';
  localStorage.setItem('wh_theme', dark ? 'dark' : 'light');
  toast(dark ? 'Тёмная тема 🌙' : 'Светлая тема ☀️');
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/warehouse/sw.js')
    .then(() => navigator.serviceWorker.ready)
    .then(() => { askQueueSize(); flushOfflineQueue(); })
    .catch(() => {});
}
updateOfflineBar();
if (TOKEN) { $('#login').classList.add('hidden'); loadList(); syncTick(); setInterval(syncTick, 30000); }
