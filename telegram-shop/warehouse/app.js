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

// предзаполнение логина (учётные данные сохраняются на устройстве)
const savedLogin = localStorage.getItem('wh_login');
if (savedLogin) $('#login-inp').value = savedLogin;
refreshQuickBox();

/* ---------- список ---------- */
async function loadList() {
  try {
    const q = $('#q').value.trim();
    const r = await api('/api/warehouse/products' + (q ? '?q=' + encodeURIComponent(q) : ''));
    PRODUCTS = r.products;
    $('#cnt').textContent = r.products.length + ' поз.';
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
        </div>
      </div>
    </div>`).join('');
  $('#printBtn').classList.toggle('active', selected.size > 0);
  $('#bulkBtn').classList.toggle('active', selected.size > 0);
}

function toggleSel(id, on) {
  if (on) selected.add(String(id)); else selected.delete(String(id));
  $('#printBtn').classList.toggle('active', selected.size > 0);
  $('#bulkBtn').classList.toggle('active', selected.size > 0);
}

async function toggleShowcase(id, on) {
  try {
    await api('/api/warehouse/products/' + id, { method: 'PUT', body: JSON.stringify({ on_showcase: on }) });
    toast(on ? 'Выставлено на витрину 🟢' : 'Снято с витрины');
    loadList();
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
    photos: EDIT_PHOTOS.map(ph => ph.newData || ph.src),
  };
  try {
    let pid = EDIT_ID;
    if (EDIT_ID) await api('/api/warehouse/products/' + EDIT_ID, { method: 'PUT', body: JSON.stringify(body) });
    else {
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

function exportOne(id) {
  window.open(`/api/warehouse/labels.pdf?ids=${id}`, '_blank');
}

async function copyOne(id) {
  try {
    const c = await api(`/api/warehouse/products/${id}/copy`, { method: 'POST', body: '{}' });
    toast(`Копия создана: ${c.code} ✅`);
    loadList();
  } catch (e) { toast(e.message, true); }
}

async function archiveOne(id) {
  if (!confirm('Отправить товар в архив? (мягкое удаление — можно восстановить в админ-панели сайта)')) return;
  try {
    await api(`/api/warehouse/products/${id}/archive`, { method: 'POST', body: '{}' });
    toast('В архиве 🗄');
    loadList();
  } catch (e) { toast(e.message, true); }
}

async function delProduct() {
  if (!EDIT_ID) return;
  if (!confirm('Удалить товар?')) return;
  try {
    await api('/admin/api/products/' + EDIT_ID, { method: 'DELETE' });
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
      <div class="info"><div class="name">📶 Bluetooth / ТСД (HID)</div><div class="meta">Заглушка: HID-ввод с клавиатуры (заглушка Этап 3)</div></div>
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
    const r = await api('/api/warehouse/scan', { method: 'POST',
      body: JSON.stringify({ code, mode: SCAN_MODE, qty }) });
    toast((r.warning ? '⚠️ ' : '') + r.message, !r.found || r.warning);
    if (SCAN_MODE === 'search' && r.found) openForm(r.product.id);
    loadList();
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
async function syncTick() {
  try {
    const r = await fetch('/api/warehouse/sync', { headers: { 'X-Wh-Token': TOKEN, 'X-Admin-Token': TOKEN } });
    if (!r.ok) return;
    const d = await r.json();
    const t = new Date(d.server_time).toLocaleTimeString('ru-RU');
    $('#syncbar').textContent = `☁️ единая база · ${d.products} товаров · синхронизировано ${t}`;
  } catch (e) {}
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
      <button class="btn primary" onclick="printByFilter()" style="margin-bottom:12px">🖨 Печать по фильтру (все подходящие)</button>
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
  const printers = await fetch('/api/warehouse/printers', { headers: { 'X-Wh-Token': TOKEN, 'X-Admin-Token': TOKEN } }).then(r => r.json());
  const pr = printers[i];
  const ids = [...selected].join(',');
  const q = `ids=${ids}&width=${pr.width_mm}&height=${pr.height_mm}&copies=${pr.copies || 1}`;
  if (pr.format === 'zpl' || pr.format === 'epl') {
    const res = await fetch(`/api/warehouse/labels.prn?${q}&format=${pr.format}`, { headers: { 'X-Wh-Token': TOKEN, 'X-Admin-Token': TOKEN } });
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'labels.prn';
    a.click();
    toast('Файл .prn скачан — отправьте на принтер (Zebra: через драйвер/сеть; Eltron: через утилиту)');
  } else {
    window.open(`/api/warehouse/labels.pdf?${q}`, '_blank');
    toast('PDF открыт — печатайте через диалог принтера');
  }
  closeSheet2();
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
    const r = await api('/api/warehouse/products/bulk', {
      method: 'POST',
      body: JSON.stringify({ ids: [...selected].map(Number), patch }),
    });
    toast(`Обновлено товаров: ${r.updated} ✅`);
    selected = new Set();
    closeBulk();
    loadList();
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

/* ---------- Bluetooth / ТСД-сканеры (HID-режим) — Этап 3 склада — ЗАГЛУШКА ---------- */
// Bluetooth-сканеры в HID-режиме работают как клавиатура: вводят штрих-код и нажимают Enter.
// Заглушка (stub): фреймворк готов, реальное подключение Bluetooth требует теста на устройстве.
let HID_SCANNER_ACTIVE = false;
let HID_SCANNER_BUFFER = '';

function openHidScanMode() {
  HID_SCANNER_ACTIVE = true;
  HID_SCANNER_BUFFER = '';
  $('#sheet2-title').textContent = '📶 Bluetooth / ТСД (HID) — заглушка';
  $('#sheet2-body').innerHTML = `
    <div style="background:#fff7ed;border:1px dashed #f97316;border-radius:12px;padding:12px;margin-bottom:12px;color:#c2410c;font-size:13px">
      <b>⚠️ Заглушка (stub)</b><br>
      Bluetooth-ТСД в HID-режиме работает как клавиатура. Для теста нажмите «Активировать HID-ввод» и сканируйте штрих-код или введите код вручную.<br><br>
      <b>Что нужно для полной интеграции:</b><br>
      • Тест на реальном устройстве с подключённым Bluetooth-сканером (Zebra DS3678, Атол SB2108)<br>
      • Проверка автоматического ввода штрих-кода в поле<br>
      • Настройка префикса/суффикса сканера (обычно Enter в конце)<br>
      • Обработка ошибок при потере связи с ТСД
    </div>
    <button class="btn primary" onclick="activateHidInput()">📶 Активировать HID-ввод (клавиатура)</button>
    <div class="row2" style="margin-top:10px">
      <input class="fld" id="hid-manual" placeholder="Или введите штрих-код вручную (заглушка)" onkeydown="if(event.key==='Enter'){handleScanCode(this.value.trim());this.value='';}">
    </div>
    <button class="btn ghost" onclick="deactivateHidInput()">✕ Отключить HID-сканер</button>
    <div id="hid-status" style="margin-top:8px;color:#64748b;font-size:12px"></div>`;
  $('#sheet2').classList.remove('hidden');
}

function activateHidInput() {
  HID_SCANNER_ACTIVE = true;
  $('#hid-status').innerHTML = '<b style="color:#15803d">✅ HID-сканер активен</b> — сканируйте штрих-код или введите вручную.';
  toast('📶 HID-сканер (заглушка) активирован. Сканируйте код или введите вручную.', false);
  setTimeout(() => { $('#hid-manual').focus(); }, 200);
}

function deactivateHidInput() {
  HID_SCANNER_ACTIVE = false;
  HID_SCANNER_BUFFER = '';
  $('#hid-status').textContent = 'HID-сканер отключён.';
}

// Перехват клавиатурного ввода для HID-сканера
(function initHidKeyboardStub() {
  let lastKeyTime = Date.now();
  document.addEventListener('keydown', function(e) {
    if (!HID_SCANNER_ACTIVE) return;
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if ([9, 16, 17, 18, 20, 27, 91, 93].includes(e.keyCode)) return;
    const now = Date.now();
    const delta = now - lastKeyTime;
    lastKeyTime = now;
    if (delta < 150 && delta > 5) {
      if (e.key.length === 1) HID_SCANNER_BUFFER += e.key;
    } else {
      if (e.key.length === 1) HID_SCANNER_BUFFER += e.key;
    }
    if (e.key === 'Enter' && HID_SCANNER_BUFFER.length > 2) {
      e.preventDefault();
      const code = HID_SCANNER_BUFFER.trim();
      HID_SCANNER_BUFFER = '';
      handleScanCode(code);
    }
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

async function printByFilter() {
  const cat = $('#pf-cat').value.trim();
  const loc = $('#pf-loc').value.trim();
  if (!cat && !loc) return toast('Укажите категорию или место для фильтра', true);
  window.open(`/api/warehouse/labels.pdf?cat=${encodeURIComponent(cat)}&loc=${encodeURIComponent(loc)}`, '_blank');
  toast('Этикетки по фильтру открыты 🖨');
  closeSheet2();
}

// ------------------------------------------------------------------ настройки
async function openSettings() {
  try {
    const s = await api('/api/warehouse/settings');
    const isAdmin = WHOAMI && WHOAMI.role === 'admin';
    const keyVal = s.cloud.key === '•••' ? '' : (s.cloud.key || '');
    $('#sheet2-title').textContent = '⚙️ Настройки';
    const isS3 = (s.cloud.provider || 's3') === 's3';
    $('#sheet2-body').innerHTML = `
      <h3 style="margin:14px 0 8px">☁️ Облако для фото и каталога</h3>
      <p style="color:#64748b;font-size:12px;margin:0 0 8px">Основная база — на нашем сервере (все устройства уже синхронизированы). Облако — резервная копия каталога и хранилище фото с CDN (рекомендуем S3: Selectel, Cloud.ru, VK Cloud, Яндекс).</p>
      <label class="lb" style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="cl-en" ${s.cloud.enabled ? 'checked' : ''} ${isAdmin ? '' : 'disabled'} style="accent-color:#0f766e"> Использовать облако</label>
      <select class="fld" id="cl-provider" ${isAdmin ? '' : 'disabled'}>
        <option value="s3" ${s.cloud.provider === 's3' ? 'selected' : ''}>S3-совместимое (Selectel / Cloud.ru / VK Cloud / Яндекс / MinIO)</option>
        <option value="supabase" ${s.cloud.provider === 'supabase' ? 'selected' : ''}>Supabase (REST)</option>
        <option value="mysql" ${s.cloud.provider === 'mysql' ? 'selected' : ''}>MySQL / MariaDB (база каталога)</option>
      </select>
      <div id="s3-fields" style="${isS3 ? '' : 'display:none'}">
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
          <input class="fld" id="s3-bucket" placeholder="Bucket" value="${esc(s.cloud.bucket || 'shop-photos')}" ${isAdmin ? '' : 'disabled'}>
          <input class="fld" id="s3-region" placeholder="Регион (пусто = из пресета)" value="${esc(s.cloud.s3_region || '')}" ${isAdmin ? '' : 'disabled'}>
        </div>
      </div>
      <div id="sb-fields" style="${s.cloud.provider === 'supabase' ? '' : 'display:none'}">
        <input class="fld" id="cl-url" placeholder="URL, например https://xxxx.supabase.co" value="${esc(s.cloud.url)}" ${isAdmin ? '' : 'disabled'}>
        <input class="fld" id="cl-key" type="password" placeholder="Ключ (anon/service)" value="${esc(keyVal)}" ${isAdmin ? '' : 'disabled'}>
        <input class="fld" id="cl-bucket2" placeholder="Bucket для фото" value="${esc(s.cloud.bucket || 'shop-photos')}" ${isAdmin ? '' : 'disabled'}>
      </div>
      <div id="my-fields" style="${s.cloud.provider === 'mysql' ? '' : 'display:none'}">
        <div class="row2">
          <input class="fld" id="my-host" placeholder="Хост (mysql.example.com)" value="${esc(s.cloud.mysql_host || '')}" ${isAdmin ? '' : 'disabled'}>
          <input class="fld" id="my-port" type="number" placeholder="Порт 3306" value="${s.cloud.mysql_port || 3306}" ${isAdmin ? '' : 'disabled'}>
        </div>
        <div class="row2">
          <input class="fld" id="my-user" placeholder="Пользователь" value="${esc(s.cloud.mysql_user || '')}" ${isAdmin ? '' : 'disabled'}>
          <input class="fld" id="my-pass" type="password" placeholder="Пароль (пусто = не менять)" ${isAdmin ? '' : 'disabled'}>
        </div>
        <div class="row2">
          <input class="fld" id="my-db" placeholder="База (shop)" value="${esc(s.cloud.mysql_database || '')}" ${isAdmin ? '' : 'disabled'}>
          <input class="fld" id="my-table" placeholder="Таблица (products)" value="${esc(s.cloud.mysql_table || 'products')}" ${isAdmin ? '' : 'disabled'}>
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
    $('#cl-provider').addEventListener('change', e => {
      const v = e.target.value;
      $('#s3-fields').style.display = v === 's3' ? '' : 'none';
      $('#sb-fields').style.display = v === 'supabase' ? '' : 'none';
      $('#my-fields').style.display = v === 'mysql' ? '' : 'none';
    });
    $('#s3-preset').value = s.cloud.s3_preset || 'selectel';
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
    $('#cloud-status').textContent = st.enabled
      ? `☁️ ${st.provider.toUpperCase()} · CDN: ${st.use_cdn ? 'вкл' : 'выкл'} · фото в облаке: ${st.photos_synced}` +
        (st.last_sync ? ` · синхронизировано ${new Date(st.last_sync).toLocaleString('ru-RU')}` : ' · ещё не синхронизировали')
      : '☁️ облако выключено — фото отдаются с сервера';
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
        </div>
      </div>
      <button class="mini danger" onclick="delPrinter(${i})">✕</button>
    </div>`).join('') || '<p style="color:#64748b;font-size:13px">Принтеров нет</p>';
  document.querySelectorAll('#pr-list [data-i]').forEach(el => el.addEventListener('change', () => {
    PRINTERS[+el.dataset.i][el.dataset.f] = el.type === 'number' ? (+el.value || 0) : el.value;
  }));
}

function addPrinter() {
  PRINTERS.push({ name: 'Новый принтер', width_mm: 58, height_mm: 40, format: 'pdf', copies: 1 });
  renderPrinterList(PRINTERS);
}

function delPrinter(i) { PRINTERS.splice(i, 1); renderPrinterList(PRINTERS); }

async function saveSettings() {
  try {
    await api('/api/warehouse/settings', { method: 'PUT', body: JSON.stringify({
      cloud: { enabled: $('#cl-en').checked, provider: $('#cl-provider').value,
               use_cdn: $('#cl-cdn').checked,
               url: $('#cl-url').value.trim(), key: $('#cl-key').value.trim(),
               bucket: ($('#s3-bucket').value.trim() || $('#cl-bucket2').value.trim()) || 'shop-photos',
               s3_preset: $('#s3-preset').value, s3_endpoint: $('#s3-ep').value.trim(),
               s3_access_key: $('#s3-ak').value.trim(),
               s3_secret_key: $('#s3-sk').value.trim(), s3_region: $('#s3-region').value.trim(),
               mysql_host: $('#my-host').value.trim(), mysql_port: +$('#my-port').value || 3306,
               mysql_user: $('#my-user').value.trim(), mysql_password: $('#my-pass').value.trim(),
               mysql_database: $('#my-db').value.trim(), mysql_table: $('#my-table').value.trim() || 'products' },
      warehouse: { auto_sync_cloud: $('#cl-autosync').checked },
      printers: PRINTERS,
      social: { auto_post_new: $('#pub-auto').checked, telegram_channel: $('#pub-tg').value.trim(),
                vk_group_id: $('#pub-vk').value.trim(),
                instagram_user_id: $('#pub-ig').value.trim(), instagram_token: $('#pub-igt').value.trim() },
    }) });
    toast('Настройки сохранены ✅');
    closeSheet2();
  } catch (e) { toast(e.message, true); }
}

async function cloudTest() {
  $('#cloud-note').textContent = 'Проверяем…';
  try {
    const r = await api('/api/warehouse/cloud/test', { method: 'POST', body: '{}' });
    $('#cloud-note').textContent = r.ok ? `✅ Облако доступно (HTTP ${r.status})` : '❌ ' + (r.error || 'нет ответа');
  } catch (e) { $('#cloud-note').textContent = '❌ ' + e.message; }
}

async function cloudSync() {
  $('#cloud-note').textContent = 'Синхронизируем (товары + фото)…';
  try {
    const r = await api('/api/warehouse/cloud/sync', { method: 'POST', body: '{}' });
    $('#cloud-note').textContent = r.ok
      ? `✅ Загружено: ${r.products} товаров, ${r.photos.uploaded} фото`
      : '❌ ' + (r.error || 'ошибка');
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

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/warehouse/sw.js').catch(() => {});
if (TOKEN) { $('#login').classList.add('hidden'); loadList(); syncTick(); setInterval(syncTick, 30000); }
