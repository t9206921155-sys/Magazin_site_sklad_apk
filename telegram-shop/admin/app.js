'use strict';
/* Админ-панель (CMS) Telegram Shop */
const $ = (sel, el) => (el || document).querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => new Intl.NumberFormat('ru-RU').format(n) + ' ₽';

const STATUS = {
  pending_payment: '⏳ ожидает оплаты', paid: '✅ оплачен', processing: '🔧 в обработке',
  shipped: '🚚 отправлен', delivered: '🎉 доставлен', cancelled: '❌ отменён',
};

let TOKEN = localStorage.getItem('tgshop_admin_token') || '';

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', 'X-Admin-Token': TOKEN, ...(opts.headers || {}) },
  });
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (res.status === 403 || res.status === 401) { showLogin(); throw new Error('Нужен вход'); }
  if (!res.ok) throw new Error((data && (data.detail || data.message)) || ('Ошибка ' + res.status));
  return data;
}

function toast(msg, err) {
  const el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 2800);
}

/* ---------------- вход ---------------- */
function showLogin() { $('#login').classList.remove('hidden'); $('#app').classList.add('hidden'); }
async function doLogin() {
  const err = $('#login-err');
  err.classList.add('hidden');
  try {
    const res = await fetch('/admin/api/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: $('#pass').value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Неверный пароль');
    TOKEN = data.token;
    localStorage.setItem('tgshop_admin_token', TOKEN);
    $('#login').classList.add('hidden');
    $('#app').classList.remove('hidden');
    init();
  } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
}
function logout() { localStorage.removeItem('tgshop_admin_token'); TOKEN = ''; showLogin(); }

/* ---------------- навигация ---------------- */
document.querySelectorAll('.side nav button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.side nav button').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  document.querySelectorAll('.tab').forEach(t => t.classList.add('hidden'));
  $('#tab-' + b.dataset.tab).classList.remove('hidden');
}));

/* ---------------- дашборд ---------------- */
async function renderDashboard() {
  const s = await api('/admin/api/dashboard');
  const orders = (await api('/admin/api/orders')).slice(0, 6);
  $('#tab-dashboard').innerHTML = `
    <h2>Дашборд</h2>
    <div class="cards">
      <div class="stat"><div class="v">${s.products}</div><div class="l">Товаров в каталоге</div></div>
      <div class="stat"><div class="v">${s.orders}</div><div class="l">Заказов всего</div></div>
      <div class="stat"><div class="v">${s.active}</div><div class="l">Активных заказов</div></div>
      <div class="stat"><div class="v">${fmt(s.revenue)}</div><div class="l">Выручка (оплачено)</div></div>
    </div>
    <div class="panel"><h3>Последние заказы</h3>
      ${orders.length ? `<table class="table"><tr><th>Заказ</th><th>Клиент</th><th>Сумма</th><th>Статус</th><th>Дата</th></tr>
      ${orders.map(o => `<tr><td><b>${esc(o.id)}</b></td><td>${esc(o.customer.name)}<br><span class="hint">${esc(o.customer.phone)}</span></td>
      <td>${fmt(o.total)}</td><td>${STATUS[o.status] || o.status}</td><td class="hint">${o.created_at.slice(0, 16).replace('T', ' ')}</td></tr>`).join('')}
      </table>` : '<div class="hint">Заказов пока нет</div>'}
    </div>`;
}

/* ---------------- товары ---------------- */
async function renderProducts() {
  const ps = await api('/admin/api/products');
  $('#tab-products').innerHTML = `
    <h2>Товары <span class="hint">(${ps.length})</span></h2>
    <button class="btn" onclick="openProductModal()">➕ Добавить товар</button>
    <div class="panel" style="margin-top:14px; padding:0">
      <table class="table">
        <tr><th></th><th>Название</th><th>Артикул</th><th>Категория</th><th>Цена</th><th>Остаток</th><th>В наличии</th><th>Avito</th><th></th></tr>
        ${ps.map(p => `<tr>
          <td><img src="${esc(p.photo)}" alt=""></td>
          <td>${esc(p.name)}${p.old_price > p.price ? `<br><span class="hint"><s>${fmt(p.old_price)}</s> → <b style="color:#e5484d">${fmt(p.price)}</b></span>` : ''}</td>
          <td class="hint">${esc(p.code || '—')}</td>
          <td>${esc(p.category || '')}</td>
          <td><b>${fmt(p.price)}</b></td>
          <td>${p.stock < 0 ? '∞' : p.stock}</td>
          <td>${p.is_archived ? '🗄' : (p.in_stock ? '✅' : '❌')}</td>
          <td>${p.avito_item_id
            ? `<a href="${esc(p.avito_url || '')}" target="_blank" title="Открыть на Avito">🔗 ${esc(p.avito_item_id)}</a>${p.avito_status === 'closed' ? ' <span class="hint">(снято)</span>' : ''}`
            : '<span class="hint">—</span>'}</td>
          <td class="row-actions">
            <button class="btn ghost small" onclick='openProductModal(${JSON.stringify(p).replace(/'/g, "&#39;")})'>Изменить</button>
            <button class="btn ghost small" onclick="genBanner(${p.id})">🖼 Баннер</button>
            <button class="btn ghost small" onclick="genVideo(${p.id})">🎬 Видео</button>
            ${p.avito_item_id
              ? `<button class="btn ghost small" onclick="avitoPost(${p.id})">🔄 Avito</button>
                 <button class="btn danger small" onclick="avitoClose(${p.id})">✕ Avito</button>`
              : `<button class="btn ghost small" onclick="avitoPost(${p.id})">📌 Avito</button>`}
            <button class="btn danger small" onclick="delProduct(${p.id})">Удалить</button>
          </td></tr>`).join('')}
      </table>
    </div>
    <div style="margin-top:12px">
      <button class="btn ghost" onclick="avitoPostAll()">📌 Выложить все товары без объявлений на Avito</button>
      <button class="btn ghost" onclick="aiGenerateAll()">🤖 ИИ: заполнить все пустые описания</button>
    </div>`;
}

async function aiGenerateAll() {
  if (!confirm('ИИ сгенерирует описания для всех товаров без описаний. Это может занять время.')) return;
  toast('Массовая генерация запущена в фоне…');
  try {
    await api('/admin/api/ai/generate-all', { method: 'POST', body: '{}' });
    toast('Запущено — результаты появятся в каталоге, прогресс в логах сервера');
  } catch (e) { toast(e.message, true); }
}
window.aiGenerateAll = aiGenerateAll;

async function genBanner(id) {
  toast('Генерируем баннер…');
  try {
    const r = await api('/admin/api/media/banner', { method: 'POST', body: JSON.stringify({ product_id: id }) });
    window.open(r.url, '_blank');
    toast('Баннер готов ✅');
  } catch (e) { toast(e.message, true); }
}
window.genBanner = genBanner;

async function loadAvitoCats() {
  $('#av-cats').innerHTML = '<span class="hint">Загружаем категории Avito…</span>';
  try {
    const cats = await api('/admin/api/avito/categories');
    $('#av-cats').innerHTML = '<label class="fld">Выберите категорию:</label>' +
      '<select class="field" id="av-cats-sel" style="margin:0">' +
      cats.map(c => `<option value="${c.id}" ${+$('#av-cat').value === c.id ? 'selected' : ''}>${esc(c.name)} (${c.id})</option>`).join('') +
      '</select>';
    $('#av-cats-sel').addEventListener('change', () => { $('#av-cat').value = $('#av-cats-sel').value; });
  } catch (e) {
    $('#av-cats').innerHTML = '<span class="hint" style="color:var(--err)">' + esc(e.message) + '</span>';
  }
}
window.loadAvitoCats = loadAvitoCats;

async function avitoPost(id) {
  toast('Выкладываем на Avito…');
  try {
    const r = await api('/admin/api/avito/post', { method: 'POST', body: JSON.stringify({ product_id: id }) });
    toast('Объявление на Avito: ' + r.item_id + ' ✅');
    renderProducts();
  } catch (e) { toast(e.message, true); }
}
window.avitoPost = avitoPost;

async function avitoClose(id) {
  if (!confirm('Снять объявление с Avito?')) return;
  try {
    await api('/admin/api/avito/close', { method: 'POST', body: JSON.stringify({ product_id: id }) });
    toast('Объявление снято с публикации');
    renderProducts();
  } catch (e) { toast(e.message, true); }
}
window.avitoClose = avitoClose;

async function avitoPostAll() {
  if (!confirm('Выложить на Avito все товары без объявлений? Это может занять время.')) return;
  toast('Пакетная выгрузка запущена…');
  try {
    await api('/admin/api/avito/post-all', { method: 'POST', body: '{}' });
    toast('Запущено — результаты в статусах товаров и логах сервера');
  } catch (e) { toast(e.message, true); }
}
window.avitoPostAll = avitoPostAll;

async function genVideo(id) {
  toast('Генерируем видео (10–30 сек)…');
  try {
    const r = await api('/admin/api/media/video', { method: 'POST', body: JSON.stringify({ product_id: id }) });
    window.open(r.url, '_blank');
    toast('Видео готово 🎬');
  } catch (e) { toast(e.message, true); }
}
window.genVideo = genVideo;

function openProductModal(p) {
  p = p || {};
  const m = document.createElement('div');
  m.className = 'modal-overlay';
  m.innerHTML = `
    <div class="modal">
      <h2>${p.id ? 'Изменить товар' : 'Новый товар'}</h2>
      <div class="form-grid">
        <div class="full"><label class="fld">Название *</label><input class="field" id="pf-name" value="${esc(p.name || '')}"></div>
        <div><label class="fld">Артикул (для 1С/импорта)</label><input class="field" id="pf-code" value="${esc(p.code || '')}"></div>
        <div><label class="fld">Категория</label><input class="field" id="pf-cat" value="${esc(p.category || '')}"></div>
        <div><label class="fld">Подкатегория</label><input class="field" id="pf-subcat" value="${esc(p.subcategory || '')}" placeholder="например: Кроссовки"></div>
        <div><label class="fld">Состояние</label><select class="field" id="pf-cond">
          <option value="new" ${p.condition !== 'used' && p.condition !== 'defect' ? 'selected' : ''}>✦ Новое</option>
          <option value="used" ${p.condition === 'used' ? 'selected' : ''}>↻ Б/у</option>
          <option value="defect" ${p.condition === 'defect' ? 'selected' : ''}>⚠ С дефектами</option>
        </select></div>
        <div><label class="fld">Цена, ₽ *</label><input class="field" id="pf-price" type="number" value="${p.price ?? 0}"></div>
        <div><label class="fld">Старая цена, ₽ (для скидки)</label><input class="field" id="pf-oldprice" type="number" value="${p.old_price ?? 0}"></div>
        <div><label class="fld">Остаток (пусто = без учёта)</label><input class="field" id="pf-stock" type="number" value="${p.stock ?? -1}"></div>
        <div><label class="fld">Закупочная цена, ₽</label><input class="field" id="pf-purchase" type="number" value="${p.purchase_price ?? 0}"></div>
        <div class="full"><label class="fld">Описание</label><textarea class="field" id="pf-desc">${esc(p.description || '')}</textarea></div>
        <div class="full"><label class="fld">Фото (файл или URL)</label><input class="field" type="file" id="pf-file" accept="image/*"></div>
        <div class="full"><input class="field" id="pf-url" placeholder="…или URL изображения" value="${p.photo && p.photo.startsWith('http') ? esc(p.photo) : ''}"></div>
        <div class="full">
          <label class="fld">Бейджи</label>
          <label class="switch-row"><input type="checkbox" id="pf-b-hit" ${(p.badges || []).includes('hit') ? 'checked' : ''}> 🔥 Хит</label>
          <label class="switch-row"><input type="checkbox" id="pf-b-new" ${(p.badges || []).includes('new') ? 'checked' : ''}> ✨ Новинка</label>
        </div>
        <div class="full">
          <label class="fld">Параметры (бренд, размер, цвет…)</label>
          <div id="pf-params"></div>
          <button type="button" class="btn ghost small" onclick="addParamRow()">＋ Добавить параметр</button>
        </div>
        <label class="switch-row full"><input type="checkbox" id="pf-stock2" ${p.in_stock !== false ? 'checked' : ''}> В наличии</label>
        <label class="switch-row full"><input type="checkbox" id="pf-archived" ${p.is_archived ? 'checked' : ''}> В архиве (скрыт из каталога и склада)</label>
      </div>
      <div style="display:flex; gap:10px; margin-top:14px; flex-wrap:wrap">
        <button class="btn" id="pf-save">Сохранить</button>
        <button class="btn ghost" onclick="this.closest('.modal-overlay').remove()">Отмена</button>
        ${p.id ? `
        <button class="btn ghost" id="ai-desc-btn" style="background:#eef2ff;color:var(--brand)">🤖 ИИ: описание и SEO</button>
        <button class="btn ghost" id="ai-ad-btn" style="background:#eef2ff;color:var(--brand)">📣 ИИ: реклама</button>
        <button class="btn ghost" id="ai-sim-btn" style="background:#eef2ff;color:var(--brand)">🔎 ИИ: аналоги в интернете</button>
        <div id="ai-sim-result" style="flex-basis:100%;font-size:13px"></div>` : ''}
      </div>
    </div>`;
  document.body.appendChild(m);
  Object.entries(p.params || {}).forEach(([k, v]) => addParamRow(k, v));
  if (p.id) {
    $('#ai-desc-btn').addEventListener('click', async () => {
      $('#ai-desc-btn').textContent = 'Генерируем…';
      try {
        const r = await api('/admin/api/ai/description', { method: 'POST', body: JSON.stringify({ product_id: p.id }) });
        $('#pf-name').value = r.title || $('#pf-name').value;
        $('#pf-desc').value = r.description || '';
        $('#ai-desc-btn').textContent = '✅ Готово';
        toast('ИИ: описание сгенерировано');
      } catch (e) { toast(e.message, true); $('#ai-desc-btn').textContent = '🤖 ИИ: описание и SEO'; }
    });
    $('#ai-ad-btn').addEventListener('click', async () => {
      $('#ai-ad-btn').textContent = 'Генерируем…';
      try {
        const r = await api('/admin/api/ai/ad', { method: 'POST', body: JSON.stringify({ product_id: p.id }) });
        await navigator.clipboard.writeText(r.post + '\n\n' + (r.hashtags || []).join(' '));
        $('#ai-ad-btn').textContent = '✅ Скопировано в буфер';
        toast('Пост для соцсетей скопирован в буфер обмена');
      } catch (e) { toast(e.message, true); $('#ai-ad-btn').textContent = '📣 ИИ: реклама'; }
    });
    $('#ai-sim-btn').addEventListener('click', async () => {
      $('#ai-sim-btn').textContent = 'Ищем…';
      try {
        const r = await api('/admin/api/ai/similar', { method: 'POST', body: JSON.stringify({ product_id: p.id }) });
        let html = `<b>Запрос:</b> ${esc(r.query)}<br>`;
        (r.results || []).forEach(x => { html += `<a href="${esc(x.url)}" target="_blank">${esc(x.title)}</a> — ${esc(x.snippet)}<br>`; });
        if (r.market_links) {
          html += r.market_links.map(l => `<a href="${esc(l.url)}" target="_blank">🔍 ${esc(l.title)}</a>`).join(' · ');
        }
        $('#ai-sim-result').innerHTML = html;
        $('#ai-sim-btn').textContent = '🔎 ИИ: аналоги в интернете';
      } catch (e) { toast(e.message, true); $('#ai-sim-btn').textContent = '🔎 ИИ: аналоги в интернете'; }
    });
  }
  $('#pf-save').addEventListener('click', async () => {
    const file = $('#pf-file').files[0];
    let photoData = '';
    if (file) {
      photoData = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(file); });
    }
    const badges = [];
    if ($('#pf-b-hit').checked) badges.push('hit');
    if ($('#pf-b-new').checked) badges.push('new');
    const params = {};
    document.querySelectorAll('#pf-params [data-pk]').forEach(inp => {
      const k = inp.value.trim();
      const v = (inp.nextElementSibling ? inp.nextElementSibling.value : '').trim();
      if (k && v) params[k] = v;
    });
    const body = {
      name: $('#pf-name').value, code: $('#pf-code').value,
      price: +$('#pf-price').value, old_price: +$('#pf-oldprice').value || 0,
      stock: $('#pf-stock').value === '' ? -1 : +$('#pf-stock').value,
      purchase_price: +$('#pf-purchase').value || 0, is_archived: $('#pf-archived').checked,
      category: $('#pf-cat').value, subcategory: $('#pf-subcat').value,
      condition: $('#pf-cond').value, params,
      description: $('#pf-desc').value,
      in_stock: $('#pf-stock2').checked, badges,
      photo_data: photoData, photo_url: $('#pf-url').value,
    };
    try {
      if (p.id) await api('/admin/api/products/' + p.id, { method: 'PUT', body: JSON.stringify(body) });
      else await api('/admin/api/products', { method: 'POST', body: JSON.stringify(body) });
      toast('Сохранено ✅');
      m.remove(); renderProducts();
    } catch (e) { toast(e.message, true); }
  });
}
window.openProductModal = openProductModal;

function addParamRow(k, v) {
  const row = document.createElement('div');
  row.style.cssText = 'display:flex; gap:8px; margin-bottom:6px';
  row.innerHTML = `<input class="field" data-pk value="${esc(k || '')}" placeholder="Название (Бренд)" style="margin:0">
    <input class="field" data-pv value="${esc(v || '')}" placeholder="Значение" style="margin:0">
    <button type="button" class="btn ghost small" onclick="this.parentElement.remove()" style="margin:0">✕</button>`;
  $('#pf-params').appendChild(row);
}
window.addParamRow = addParamRow;

async function delProduct(id) {
  if (!confirm('Удалить товар?')) return;
  try { await api('/admin/api/products/' + id, { method: 'DELETE' }); toast('Товар удалён'); renderProducts(); }
  catch (e) { toast(e.message, true); }
}
window.delProduct = delProduct;

/* ---------------- заказы ---------------- */
async function renderOrders() {
  const orders = await api('/admin/api/orders');
  $('#tab-orders').innerHTML = `
    <h2>Заказы <span class="hint">(${orders.length})</span></h2>
    ${orders.map(o => `
    <div class="panel">
      <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px">
        <b>${esc(o.id)}</b>
        <span>${STATUS[o.status] || esc(o.status)}</span>
        <b>${fmt(o.total)}</b>
        <span class="hint">${o.created_at.slice(0, 16).replace('T', ' ')}</span>
      </div>
      <div class="hint" style="margin:8px 0">${o.items.map(i => esc(i.name) + ' × ' + i.qty).join(', ')}</div>
      <div class="hint" style="margin-bottom:10px">
        👤 ${esc(o.customer.name)} • 📞 ${esc(o.customer.phone)} • 🏠 ${esc(o.customer.address || 'самовывоз')}
        ${o.customer.comment ? ' • 💬 ' + esc(o.customer.comment) : ''}
        • Доставка: ${esc(o.delivery.label)} • Оплата: ${esc(o.payment_method || '—')}
        ${o.payment && o.payment.status
          ? ' • ' + (o.payment.status === 'succeeded' ? '💵 оплачен'
            : (o.payment.status === 'verifying' ? '🕓 проверка перевода' : '⏳ ждёт оплату'))
          : ''}
        ${o.synced ? ' • 🔁 выгружен в 1С' : ''}
      </div>
      ${o.payment && o.payment.provider === 'transfer' && ['pending', 'verifying'].includes(o.payment.status) && o.status === 'pending_payment'
        ? `<div class="row-actions" style="margin:8px 0"><button class="btn small" onclick="confirmTransfer('${o.id}')">✅ Подтвердить перевод</button></div>` : ''}
      <div style="display:flex; gap:8px; align-items:center; margin-bottom:10px">
        <span class="hint">Трек/номер в службе доставки:</span>
        <input class="field" style="flex:0 0 220px; margin:0" id="trk-${esc(o.id)}" value="${esc(o.delivery.tracking || '')}" placeholder="не задан">
        <button class="btn ghost small" onclick="saveTracking('${o.id}')">Сохранить</button>
      </div>
      <div class="row-actions">
        ${statusButtons(o).map(s => `<button class="btn ${s.cls}" onclick="setOrderStatus('${o.id}','${s.st}')">${s.lbl}</button>`).join('')}
      </div>
    </div>`).join('') || '<div class="panel hint">Заказов пока нет</div>'}`;
}

function statusButtons(o) {
  const flow = { paid: ['paid', 'processing', 'shipped', 'delivered'], pending_payment: [] };
  const seq = ['paid', 'processing', 'shipped', 'delivered'];
  const out = [];
  if (o.status === 'pending_payment') {
    out.push({ st: 'paid', lbl: '✅ Отметить оплаченным', cls: 'small' });
  } else {
    const i = seq.indexOf(o.status);
    if (i >= 0 && i < seq.length - 1) out.push({ st: seq[i + 1], lbl: '→ ' + STATUS[seq[i + 1]], cls: 'small' });
  }
  if (o.status !== 'cancelled' && o.status !== 'delivered') out.push({ st: 'cancelled', lbl: '❌ Отменить', cls: 'danger small' });
  return out;
}

async function confirmTransfer(id) {
  if (!confirm('Подтвердить оплату переводом по заказу ' + id + '?')) return;
  try {
    await api('/admin/api/orders/' + id + '/confirm-payment', { method: 'POST', body: '{}' });
    toast('Оплата подтверждена ✅');
    renderOrders();
  } catch (e) { toast(e.message, true); }
}
window.confirmTransfer = confirmTransfer;

async function setOrderStatus(id, status) {
  try { await api('/admin/api/orders/' + id + '/status', { method: 'POST', body: JSON.stringify({ status }) }); toast('Статус обновлён'); renderOrders(); }
  catch (e) { toast(e.message, true); }
}
window.setOrderStatus = setOrderStatus;

async function saveTracking(id) {
  const v = $('#trk-' + id).value.trim();
  try { await api('/admin/api/orders/' + id + '/tracking', { method: 'POST', body: JSON.stringify({ tracking: v }) }); toast('Трек-номер сохранён'); }
  catch (e) { toast(e.message, true); }
}
window.saveTracking = saveTracking;


/* ---------------- продавцы (маркетплейс) ---------------- */
async function renderSellers() {
  const sellers = await api('/admin/api/sellers');
  const payouts = await api('/admin/api/payouts');
  const PLANS = (window.TARIFFS && window.TARIFFS.seller_plans) || [];
  const planName = id => (PLANS.find(p => p.id === id) || { name: id || '—' }).name;
  const vStatus = x => x.verification_status === 'verified' ? '✅ проверен'
    : x.verification_status === 'pending' ? '⏳ на проверке'
    : x.verification_status === 'rejected' ? '❌ отклонён' : '—';
  $('#tab-sellers').innerHTML = `
    <h2>Продавцы маркетплейса <span class="hint">(${sellers.length})</span></h2>
    <div class="panel" style="padding:0">
      <table class="table">
        <tr><th>Витрина</th><th>Контакты</th><th>Тариф</th><th>Комиссия</th><th>Баланс / холд</th><th>Верификация</th><th>Статус</th><th></th></tr>
        ${sellers.map(x => `<tr>
          <td><b>${esc(x.store_name)}</b><br><span class="hint">/seller/${esc(x.slug)}</span></td>
          <td>${esc(x.phone)}<br><span class="hint">${esc(x.email || '')}</span></td>
          <td><select class="field" style="margin:0; max-width:130px" onchange="setSellerPlan(${x.id}, this.value)">
            ${PLANS.map(p => `<option value="${p.id}" ${(x.plan || 'start') === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
          </select></td>
          <td><input class="field" id="sc-${x.id}" type="number" value="${x.commission_percent || 15}" style="width:70px; margin:0" onchange="setCommission(${x.id}, this.value)"></td>
          <td><b>${fmt(x.balance)}</b>${x.held_balance ? `<br><span class="hint">🔒 холд: ${fmt(x.held_balance)}</span>
            <button class="btn ghost small" onclick="releaseHeld(${x.id})">Разморозить</button>` : ''}</td>
          <td>${vStatus(x)}${x.verification_status === 'pending' ? `<br><button class="btn small" onclick="sellerVerify(${x.id},'verified')">✅ Подтвердить</button>
            <button class="btn danger small" onclick="sellerVerify(${x.id},'rejected')">Отклонить</button>` : x.verification_status === 'verified' ? `<br><button class="btn ghost small" onclick="sellerVerify(${x.id},'unverified')">Снять</button>` : ''}</td>
          <td>${x.status === 'active' ? '✅ активен' : x.status === 'pending' ? '⏳ ждёт' : '⛔ блок'}</td>
          <td class="row-actions">
            ${x.status !== 'active' ? `<button class="btn small" onclick="sellerStatus(${x.id},'active')">Одобрить</button>` : ''}
            ${x.status === 'active' ? `<button class="btn danger small" onclick="sellerStatus(${x.id},'blocked')">Заблокировать</button>` : ''}
            <a class="btn ghost small" href="/seller/${esc(x.slug)}" target="_blank">Витрина</a>
          </td></tr>`).join('') || '<tr><td colspan="8" class="hint">Продавцов пока нет</td></tr>'}
      </table>
    </div>
    <div class="panel">
      <h3>📈 Отчёт по комиссиям за период</h3>
      <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end">
        <div><label class="fld">С</label><input class="field" type="date" id="cr-from" style="margin:0"></div>
        <div><label class="fld">По</label><input class="field" type="date" id="cr-to" style="margin:0"></div>
        <button class="btn" onclick="loadCommissionReport()">Сформировать</button>
        <button class="btn ghost" onclick="downloadCommissionCsv()">⬇️ CSV</button>
        <button class="btn ghost" onclick="downloadCommissionPdf()">⬇️ PDF</button>
      </div>
      <div id="cr-report" class="hint" style="margin-top:10px">Выберите период и нажмите «Сформировать».</div>
    </div>
    <div class="panel">
      <h3>💰 Выплата продавцу</h3>
      <div style="display:flex; gap:10px; flex-wrap:wrap">
        <select class="field" id="po-seller" style="max-width:260px; margin:0">${sellers.filter(x => x.status === 'active').map(x => `<option value="${x.id}">${esc(x.store_name)} (${fmt(x.balance)})</option>`).join('')}</select>
        <input class="field" id="po-amount" type="number" placeholder="Сумма" style="max-width:160px; margin:0">
        <button class="btn" onclick="createPayout()">Выплатить</button>
      </div>
    </div>
    <div class="panel" style="padding:0">
      <h3>История выплат</h3>
      <table class="table">
        <tr><th>Дата</th><th>Продавец</th><th>Сумма</th><th>Статус</th><th>Примечание</th></tr>
        ${payouts.map(x => { const sl = sellers.find(s => s.id === x.seller_id); return `<tr>
          <td class="hint">${x.created_at.slice(0, 10)}</td><td>${esc(sl ? sl.store_name : x.seller_id)}</td>
          <td><b>${fmt(x.amount)}</b></td><td>${x.status === 'paid' ? '✅ выплачено' : '⏳ запрошена'}</td>
          <td class="hint">${esc(x.note || '')}</td>
          <td>${x.status === 'requested' ? `<button class="btn small" onclick="confirmPayout(${x.id})">✅ Подтвердить выплату</button>` : ''}</td></tr>`; }).join('') || '<tr><td colspan="6" class="hint">Выплат не было</td></tr>'}
      </table>
    </div>`;
}
async function sellerStatus(id, status) {
  try { await api('/admin/api/sellers/' + id + '/status', { method: 'POST', body: JSON.stringify({ status }) }); toast('Статус обновлён'); renderSellers(); }
  catch (e) { toast(e.message, true); }
}
window.sellerStatus = sellerStatus;
async function setSellerPlan(id, plan) {
  try { await api('/admin/api/sellers/' + id + '/plan', { method: 'POST', body: JSON.stringify({ plan }) }); toast('Тариф назначен'); renderSellers(); }
  catch (e) { toast(e.message, true); }
}
window.setSellerPlan = setSellerPlan;
async function sellerVerify(id, status) {
  try { await api('/admin/api/sellers/' + id + '/verify', { method: 'POST', body: JSON.stringify({ status }) }); toast('Верификация обновлена'); renderSellers(); }
  catch (e) { toast(e.message, true); }
}
window.sellerVerify = sellerVerify;
async function releaseHeld(id) {
  try { const r = await api('/admin/api/sellers/' + id + '/release-held', { method: 'POST', body: '{}' }); toast('Разморожено: ' + fmt(r.released)); renderSellers(); }
  catch (e) { toast(e.message, true); }
}
window.releaseHeld = releaseHeld;
async function setCommission(id, percent) {
  try { await api('/admin/api/sellers/' + id + '/commission', { method: 'POST', body: JSON.stringify({ percent: +percent || 15 }) }); toast('Комиссия обновлена'); }
  catch (e) { toast(e.message, true); }
}
window.setCommission = setCommission;
let CR_DATA = null;
async function loadCommissionReport() {
  const from = $('#cr-from').value, to = $('#cr-to').value;
  $('#cr-report').textContent = 'Считаем…';
  try {
    const r = await api('/admin/api/reports/sellers?date_from=' + from + '&date_to=' + to);
    CR_DATA = r;
    const t = r.totals;
    $('#cr-report').innerHTML = `
      <table class="table">
        <tr><th>Продавец</th><th>Заказов</th><th>Продажи</th><th>Комиссия площадки</th><th>К выплате продавцу</th></tr>
        ${r.rows.map(x => `<tr><td>${esc(x.store_name)}</td><td>${x.orders}</td><td>${fmt(x.sales)}</td>
          <td style="color:#16a34a"><b>${fmt(x.commission)}</b></td><td>${fmt(x.net)}</td></tr>`).join('')
          || '<tr><td colspan="5" class="hint">За период нет продаж у продавцов</td></tr>'}
        <tr><td><b>Итого</b></td><td>${r.rows.length} продавц.</td><td><b>${fmt(t.sales)}</b></td>
          <td style="color:#16a34a"><b>${fmt(t.commission)}</b></td><td><b>${fmt(t.net)}</b></td></tr>
      </table>
      <div class="hint" style="margin-top:8px">Выплачено за период: <b>${fmt(t.payouts)}</b> ·
      Ваша прибыль (комиссия − выплаченное): <b>${fmt(t.commission - t.payouts)}</b></div>`;
  } catch (e) { $('#cr-report').textContent = '❌ ' + e.message; }
}
window.loadCommissionReport = loadCommissionReport;

function downloadCommissionCsv() {
  if (!CR_DATA) return toast('Сначала сформируйте отчёт', true);
  const rows = [['Продавец','Заказов','Продажи','Комиссия площадки','К выплате продавцу']];
  CR_DATA.rows.forEach(x => rows.push([x.store_name, x.orders, x.sales, x.commission, x.net]));
  rows.push(['Итого','',CR_DATA.totals.sales,CR_DATA.totals.commission,CR_DATA.totals.net]);
  const csv = '\ufeff' + rows.map(r => r.join(';')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  a.download = 'commission-report.csv';
  a.click();
  toast('Отчёт скачан ✅');
}
window.downloadCommissionCsv = downloadCommissionCsv;

async function downloadCommissionPdf() {
  const from = $('#cr-from').value, to = $('#cr-to').value;
  try {
    const res = await fetch('/admin/api/reports/sellers.pdf?date_from=' + from + '&date_to=' + to,
      { headers: { 'X-Admin-Token': TOKEN } });
    if (!res.ok) throw new Error('Ошибка генерации PDF');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'commission-report.pdf';
    a.click();
    toast('PDF-отчёт скачан ✅');
  } catch (e) { toast(e.message, true); }
}
window.downloadCommissionPdf = downloadCommissionPdf;

async function confirmPayout(id) {
  if (!confirm('Подтвердить выплату? Деньги уже переведены продавцу?')) return;
  try { await api('/admin/api/payouts/' + id + '/status', { method: 'POST', body: JSON.stringify({ status: 'paid' }) }); toast('Выплата подтверждена ✅'); renderSellers(); }
  catch (e) { toast(e.message, true); }
}
window.confirmPayout = confirmPayout;

async function createPayout() {
  const sid = +$('#po-seller').value;
  const amount = +$('#po-amount').value;
  if (!sid || !amount || amount <= 0) return toast('Выберите продавца и сумму', true);
  try { await api('/admin/api/payouts', { method: 'POST', body: JSON.stringify({ seller_id: sid, amount }) }); toast('Выплата проведена ✅'); renderSellers(); }
  catch (e) { toast(e.message, true); }
}
window.createPayout = createPayout;

/* ---------------- промокоды ---------------- */
async function renderPromos() {
  const ps = await api('/admin/api/promos');
  $('#tab-promos').innerHTML = `
    <h2>Промокоды <span class="hint">(${ps.length})</span></h2>
    <div class="panel">
      <h3>Создать промокод</h3>
      <div class="form-grid">
        <div><label class="fld">Код</label><input class="field" id="pr-code" placeholder="SALE10"></div>
        <div><label class="fld">Тип</label><select class="field" id="pr-type"><option value="percent">Процент (%)</option><option value="fixed">Фикс. сумма (₽)</option></select></div>
        <div><label class="fld">Значение</label><input class="field" id="pr-value" type="number" value="10"></div>
        <div><label class="fld">Минимальная сумма заказа (0 = без)</label><input class="field" id="pr-min" type="number" value="0"></div>
        <div><label class="fld">Лимит использований (0 = без)</label><input class="field" id="pr-max" type="number" value="0"></div>
        <div><label class="fld">Действует до (пусто = бессрочно)</label><input class="field" id="pr-exp" type="date"></div>
        <div class="full"><label class="fld">Описание</label><input class="field" id="pr-desc" placeholder="Скидка на первый заказ"></div>
      </div>
      <button class="btn" onclick="createPromo()">➕ Создать</button>
    </div>
    <div class="panel" style="padding:0">
      <table class="table">
        <tr><th>Код</th><th>Тип</th><th>Значение</th><th>Мин. сумма</th><th>Использовано</th><th>Лимит</th><th>До</th><th>Статус</th><th></th></tr>
        ${ps.map(p => `<tr>
          <td><b>${esc(p.code)}</b><br><span class="hint">${esc(p.description || '')}</span></td>
          <td>${p.type === 'percent' ? '%' : '₽'}</td><td>${p.value}</td>
          <td>${p.min_subtotal || '—'}</td><td>${p.used}</td><td>${p.max_uses || '∞'}</td>
          <td class="hint">${esc(p.expires_at || '—')}</td>
          <td>${p.enabled ? '✅' : '⛔'}</td>
          <td><button class="btn danger small" onclick="delPromo('${esc(p.code)}')">Удалить</button></td>
        </tr>`).join('') || '<tr><td colspan="9" class="hint">Промокодов нет</td></tr>'}
      </table>
    </div>`;
}

async function createPromo() {
  try {
    await api('/admin/api/promos', { method: 'POST', body: JSON.stringify({
      code: $('#pr-code').value, type: $('#pr-type').value,
      value: +$('#pr-value').value, min_subtotal: +$('#pr-min').value || 0,
      max_uses: +$('#pr-max').value || 0, expires_at: $('#pr-exp').value,
      description: $('#pr-desc').value, enabled: true,
    }) });
    toast('Промокод создан ✅');
    renderPromos();
  } catch (e) { toast(e.message, true); }
}
window.createPromo = createPromo;

async function delPromo(code) {
  if (!confirm('Удалить промокод ' + code + '?')) return;
  try { await api('/admin/api/promos/' + code, { method: 'DELETE' }); toast('Удалён'); renderPromos(); }
  catch (e) { toast(e.message, true); }
}
window.delPromo = delPromo;

/* ---------------- отзывы ---------------- */
async function renderReviews() {
  const r = await api('/admin/api/reviews');
  $('#tab-reviews').innerHTML = `
    <h2>Отзывы <span class="hint">(${r.reviews.length})</span></h2>
    <div class="panel" style="padding:0">
      <table class="table">
        <tr><th>Товар</th><th>Автор</th><th>Оценка</th><th>Отзыв</th><th>Статус</th><th></th></tr>
        ${r.reviews.map(x => `<tr>
          <td>${esc((r.product_names || {})[String(x.product_id)] || x.product_id)}</td>
          <td>${esc(x.author)}</td>
          <td>${'★'.repeat(x.rating)}${'☆'.repeat(5 - x.rating)}</td>
          <td style="max-width:320px">${esc(x.text)}</td>
          <td>${x.status === 'approved' ? '✅ опубл.' : '⏳ модерация'}</td>
          <td class="row-actions">
            ${x.status !== 'approved' ? `<button class="btn ghost small" onclick="approveReview(${x.id})">Опубликовать</button>` : ''}
            <button class="btn danger small" onclick="delReview(${x.id})">Удалить</button>
          </td></tr>`).join('') || '<tr><td colspan="6" class="hint">Отзывов пока нет</td></tr>'}
      </table>
    </div>`;
}
async function approveReview(id) {
  try { await api('/admin/api/reviews/' + id + '/approve', { method: 'POST', body: '{}' }); toast('Отзыв опубликован ✅'); renderReviews(); }
  catch (e) { toast(e.message, true); }
}
window.approveReview = approveReview;
async function delReview(id) {
  if (!confirm('Удалить отзыв?')) return;
  try { await api('/admin/api/reviews/' + id, { method: 'DELETE' }); toast('Отзыв удалён'); renderReviews(); }
  catch (e) { toast(e.message, true); }
}
window.delReview = delReview;

/* ---------------- блог ---------------- */
async function renderBlog() {
  const posts = await api('/admin/api/blog');
  $('#tab-blog').innerHTML = `
    <h2>Блог <span class="hint">(${posts.length})</span></h2>
    <button class="btn" onclick="openPostModal()">➕ Новая статья</button>
    <div class="panel" style="margin-top:14px; padding:0">
      <table class="table">
        <tr><th>Заголовок</th><th>Slug</th><th>Дата</th><th>Статус</th><th></th></tr>
        ${posts.map(x => `<tr>
          <td>${esc(x.title)}</td><td class="hint">/${esc(x.slug)}</td>
          <td class="hint">${x.created_at.slice(0, 10)}</td>
          <td>${x.published ? '✅ опубл.' : '⏳ черновик'}</td>
          <td class="row-actions">
            <button class="btn ghost small" onclick='openPostModal(${JSON.stringify(x).replace(/'/g, "&#39;")})'>Изменить</button>
            <a class="btn ghost small" href="/blog/${esc(x.slug)}" target="_blank">Открыть</a>
            <button class="btn danger small" onclick="delPost(${x.id})">Удалить</button>
          </td></tr>`).join('') || '<tr><td colspan="5" class="hint">Статей пока нет</td></tr>'}
      </table>
    </div>`;
}

function openPostModal(x) {
  x = x || {};
  const m = document.createElement('div');
  m.className = 'modal-overlay';
  m.innerHTML = `
    <div class="modal">
      <h2>${x.id ? 'Изменить статью' : 'Новая статья'}</h2>
      <div class="form-grid">
        <div class="full"><label class="fld">Заголовок</label><input class="field" id="pt-title" value="${esc(x.title || '')}"></div>
        <div><label class="fld">Slug (латиницей через дефис)</label><input class="field" id="pt-slug" value="${esc(x.slug || '')}"></div>
        <div class="full"><label class="fld">Краткое описание (для списка и SEO)</label><textarea class="field" id="pt-excerpt">${esc(x.excerpt || '')}</textarea></div>
        <div class="full"><label class="fld">Текст статьи (абзацы — пустой строкой)</label><textarea class="field" id="pt-content" style="min-height:220px">${esc(x.content || '')}</textarea></div>
        <div class="full"><label class="fld">Обложка (URL)</label><input class="field" id="pt-cover" value="${esc(x.cover || '')}"></div>
        <label class="switch-row full"><input type="checkbox" id="pt-pub" ${x.published ? 'checked' : ''}> Опубликована</label>
        <div class="full"><label class="fld">🤖 ИИ-генерация: тема (или id товара для обзора)</label>
          <div style="display:flex;gap:8px">
            <input class="field" id="pt-ai" placeholder="как выбрать беспроводные наушники" style="margin:0">
            <button class="btn ghost" id="pt-ai-btn" type="button">Сгенерировать</button>
          </div>
        </div>
      </div>
      <div style="display:flex; gap:10px; margin-top:14px">
        <button class="btn" id="pt-save">Сохранить</button>
        <button class="btn ghost" onclick="this.closest('.modal-overlay').remove()">Отмена</button>
      </div>
    </div>`;
  document.body.appendChild(m);
  $('#pt-ai-btn').addEventListener('click', async () => {
    const v = $('#pt-ai').value.trim();
    if (!v) return toast('Введите тему или id товара', true);
    $('#pt-ai-btn').textContent = 'Генерируем…';
    try {
      const body = /^\d+$/.test(v) ? { product_id: +v } : { topic: v };
      const r = await api('/admin/api/blog/ai', { method: 'POST', body: JSON.stringify(body) });
      $('#pt-title').value = r.title || '';
      $('#pt-slug').value = r.slug || '';
      $('#pt-excerpt').value = r.excerpt || '';
      $('#pt-content').value = r.content || '';
      $('#pt-ai-btn').textContent = '✅ Готово';
    } catch (e) { toast(e.message, true); $('#pt-ai-btn').textContent = 'Сгенерировать'; }
  });
  $('#pt-save').addEventListener('click', async () => {
    try {
      await api('/admin/api/blog', { method: 'POST', body: JSON.stringify({
        id: x.id || 0, title: $('#pt-title').value, slug: $('#pt-slug').value,
        excerpt: $('#pt-excerpt').value, content: $('#pt-content').value,
        cover: $('#pt-cover').value, published: $('#pt-pub').checked,
      }) });
      toast('Сохранено ✅');
      m.remove(); renderBlog();
    } catch (e) { toast(e.message, true); }
  });
}
window.openPostModal = openPostModal;
async function delPost(id) {
  if (!confirm('Удалить статью?')) return;
  try { await api('/admin/api/blog/' + id, { method: 'DELETE' }); toast('Удалена'); renderBlog(); }
  catch (e) { toast(e.message, true); }
}
window.delPost = delPost;

/* ---------------- рассылка ---------------- */
async function renderBroadcast() {
  const users = (await api('/admin/api/reports')).users;
  $('#tab-broadcast').innerHTML = `
    <h2>Рассылка в Telegram</h2>
    <div class="panel">
      <p class="hint">Сообщение получат <b>${users}</b> пользователей, которые открывали бота.
      Отправка идёт со скоростью ~20 сообщений/сек (лимит Telegram).</p>
      <textarea class="field" id="bc-text" style="min-height:140px" placeholder="🎉 Только сегодня — скидка 15% на всё по промокоду SALE15!"></textarea>
      <button class="btn" onclick="sendBroadcast()">📣 Отправить рассылку</button>
      <div class="hint" style="margin-top:8px" id="bc-status"></div>
    </div>
    <div class="panel hint">
      Тот же функционал доступен в боте командой <b>/broadcast текст</b> (для админов).
      Статистика отправки появится в логах сервера после завершения.
    </div>`;
}

async function sendBroadcast() {
  const text = $('#bc-text').value.trim();
  if (!text) return toast('Введите текст рассылки', true);
  const btn = document.querySelector('#tab-broadcast .btn');
  btn.disabled = true;
  $('#bc-status').textContent = 'Рассылка запущена в фоне…';
  try {
    const r = await api('/admin/api/broadcast', { method: 'POST', body: JSON.stringify({ text }) });
    $('#bc-status').textContent = `Рассылка запущена (получателей: ${r.users}). Логи — в консоли сервера.`;
  } catch (e) { toast(e.message, true); $('#bc-status').textContent = ''; }
  btn.disabled = false;
}
window.sendBroadcast = sendBroadcast;

/* ---------------- отчёты ---------------- */
async function renderReports() {
  const r = await api('/admin/api/reports');
  const f = r.funnel || {};
  const views = f.view_product || 0;
  const adds = f.add_to_cart || 0;
  const checks = f.checkout || 0;
  const paid = f.paid || 0;
  const pct = (a, b) => b ? Math.round(a / b * 100) + '%' : '—';
  const maxDay = Math.max(1, ...(r.by_day || []).map(d => d.revenue));
  $('#tab-reports').innerHTML = `
    <h2>Отчёты</h2>
    <div class="cards">
      <div class="stat"><div class="v">${r.today.orders}</div><div class="l">Заказов сегодня</div></div>
      <div class="stat"><div class="v">${fmt(r.today.revenue)}</div><div class="l">Выручка сегодня</div></div>
      <div class="stat"><div class="v">${r.users}</div><div class="l">Пользователей</div></div>
      <div class="stat"><div class="v">${fmt(r.stats.revenue)}</div><div class="l">Выручка всего</div></div>
    </div>
    <div class="panel">
      <h3>Воронка продаж</h3>
      ${[
        ['Просмотры товаров', views, null],
        ['Добавили в корзину', adds, pct(adds, views)],
        ['Оформили заказ', checks, pct(checks, adds)],
        ['Оплатили', paid, pct(paid, checks)],
      ].map(([lbl, val, conv]) => `
        <div style="margin-bottom:10px">
          <div class="hint" style="display:flex;justify-content:space-between"><span>${lbl}</span><span>${val}${conv ? ' · ' + conv : ''}</span></div>
          <div style="background:var(--bg);border-radius:8px;height:12px;overflow:hidden">
            <div style="height:100%;width:${Math.min(100, Math.round(val / Math.max(1, views) * 100))}%;background:linear-gradient(90deg,#1e88ff,#6a3df5)"></div>
          </div>
        </div>`).join('')}
    </div>
    <div class="panel">
      <h3>Выручка по дням (14 дней)</h3>
      <div style="display:flex;align-items:flex-end;gap:6px;height:140px;padding-top:10px">
        ${(r.by_day || []).map(d => `
          <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px" title="${d.date}: ${fmt(d.revenue)}">
            <span class="hint" style="font-size:10px">${fmt(d.revenue).replace(' ₽', '')}</span>
            <div style="width:100%;max-width:34px;height:${Math.round(d.revenue / maxDay * 90)}px;background:${d.revenue ? 'linear-gradient(180deg,#1e88ff,#6a3df5)' : '#e4e7ec'};border-radius:6px 6px 2px 2px"></div>
            <span class="hint" style="font-size:10px">${d.date.slice(5)}</span>
          </div>`).join('')}
      </div>
    </div>
    <div class="panel">
      <h3>Топ товаров</h3>
      ${r.top_products.length ? `<table class="table"><tr><th>Товар</th><th>Продано, шт</th></tr>
      ${r.top_products.map(p => `<tr><td>${esc(p.name)}</td><td><b>${p.qty}</b></td></tr>`).join('')}</table>`
        : '<div class="hint">Продаж пока нет</div>'}
    </div>
    <div class="panel">
      <h3>Экспорт</h3>
      <div class="row-actions">
        <button class="btn" onclick="exportCsv('orders')">⬇️ Заказы (CSV)</button>
        <button class="btn ghost" onclick="exportCsv('products')">⬇️ Товары (CSV)</button>
      </div>
    </div>`;
}

async function exportCsv(kind) {
  try {
    const res = await fetch('/admin/api/export/' + kind, { headers: { 'X-Admin-Token': TOKEN } });
    if (!res.ok) throw new Error('Ошибка экспорта');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = kind + '.csv';
    a.click();
    toast('Файл ' + kind + '.csv скачан ✅');
  } catch (e) { toast(e.message, true); }
}
window.exportCsv = exportCsv;

/* ---------------- настройки ---------------- */
let SETTINGS = null;
async function renderSettings() {
  SETTINGS = await api('/admin/api/settings');
  const s = SETTINGS;
  const d = s.delivery;
  $('#tab-settings').innerHTML = `
    <h2>Настройки магазина</h2>
    <div class="panel">
      <h3>Основное</h3>
      <div class="form-grid">
        <div><label class="fld">Название магазина</label><input class="field" id="st-name" value="${esc(s.shop_name)}"></div>
        <div><label class="fld">Валюта</label><input class="field" id="st-curr" value="${esc(s.currency)}"></div>
      </div>
    </div>
    <div class="panel">
      <h3>Доставка</h3>
      <div id="del-rows"></div>
      <button class="btn ghost small" onclick="addDelRow()">＋ Добавить способ</button>
      <h3>СДЭК (расчёт стоимости по API)</h3>
      <div class="switch-row"><input type="checkbox" id="cdek-en" ${s.cdek.enabled ? 'checked' : ''}> Включить расчёт СДЭК при оформлении</div>
      <div class="form-grid">
        <div><label class="fld">Аккаунт СДЭК</label><input class="field" id="cdek-acc" value="${esc(s.cdek.account)}" placeholder="пусто = тестовый аккаунт"></div>
        <div><label class="fld">Пароль СДЭК</label><input class="field" id="cdek-pass" value="${esc(s.cdek.password)}" placeholder="пусто = тестовый"></div>
        <div><label class="fld">Город отправки (код СДЭК)</label><input class="field" id="cdek-from" type="number" value="${s.cdek.from_city}"></div>
      </div>
      <h3>5POST — постаматы и ПВЗ X5</h3>
      <div class="switch-row"><input type="checkbox" id="fp-en" ${s.fivepost.enabled ? 'checked' : ''}> Включить способ доставки «5POST»</div>
      <div class="form-grid">
        <div><label class="fld">API-ключ 5POST (от менеджера после договора)</label><input class="field" id="fp-key" value="${esc(s.fivepost.api_key)}"></div>
        <div><label class="fld">ID склада забора (warehouse)</label><input class="field" id="fp-wh" value="${esc(s.fivepost.warehouse_id)}"></div>
        <div><label class="fld">Бренд отправителя (в СМС клиенту)</label><input class="field" id="fp-brand" value="${esc(s.fivepost.brand_name)}" placeholder="${esc(s.shop_name)}"></div>
      </div>
      <div class="switch-row"><input type="checkbox" id="fp-test" ${s.fivepost.test_mode ? 'checked' : ''}> Тестовая среда 5POST (api-preprod-omni.x5.ru)</div>
      <h3>Яндекс Доставка</h3>
      <div class="switch-row"><input type="checkbox" id="yx-en" ${s.yandex.enabled ? 'checked' : ''}> Включить способ доставки «Яндекс Доставка»</div>
      <div class="form-grid">
        <div><label class="fld">API-токен (delivery.yandex.ru → Интеграция)</label><input class="field" id="yx-token" value="${esc(s.yandex.token)}"></div>
        <div><label class="fld">Адрес склада отправки</label><input class="field" id="yx-wh" value="${esc(s.yandex.warehouse_address)}" placeholder="Россия, Москва, ул. …"></div>
      </div>
      <div class="switch-row"><input type="checkbox" id="yx-test" ${s.yandex.test_mode ? 'checked' : ''}> Тестовая среда</div>
      <h3>Продажи</h3>
      <div><label class="fld">Бесплатная доставка от суммы, ₽ (0 = выключено)</label><input class="field" id="free-from" type="number" value="${s.free_delivery_from || 0}"></div>
      <h3>Маркетплейс (продавцы)</h3>
      <div class="switch-row"><input type="checkbox" id="mp-en" ${s.marketplace.enabled ? 'checked' : ''}> Разрешить регистрацию продавцов</div>
      <div class="switch-row"><input type="checkbox" id="mp-auto" ${s.marketplace.auto_approve_sellers ? 'checked' : ''}> Подтверждать продавцов автоматически</div>
      <div><label class="fld">Комиссия площадки по умолчанию, %</label><input class="field" id="mp-comm" type="number" value="${s.marketplace.commission_percent || 15}"></div>
      <h3>📧 Email-уведомления продавцам (SMTP)</h3>
      <div class="switch-row"><input type="checkbox" id="sm-en" ${s.smtp.enabled ? 'checked' : ''}> Включить отправку писем</div>
      <div class="form-grid">
        <div><label class="fld">SMTP-сервер</label><input class="field" id="sm-host" value="${esc(s.smtp.host)}" placeholder="smtp.yandex.ru"></div>
        <div><label class="fld">Порт</label><input class="field" id="sm-port" type="number" value="${s.smtp.port || 465}"></div>
        <div><label class="fld">Логин</label><input class="field" id="sm-user" value="${esc(s.smtp.user)}"></div>
        <div><label class="fld">Пароль (пусто = не менять)</label><input class="field" id="sm-pass" type="password" placeholder="••••••"></div>
        <div><label class="fld">От кого (email)</label><input class="field" id="sm-from" value="${esc(s.smtp.from_email)}" placeholder="shop@example.com"></div>
      </div>
      <p class="hint">Письма отправляются продавцам: о новом заказе, об одобрении витрины и о выплатах.
      Для Яндекс.Почты используйте «пароль приложения».</p>
      <h3>Лояльность и отзывы</h3>
      <div class="switch-row"><input type="checkbox" id="loy-en" ${s.loyalty.enabled ? 'checked' : ''}> 💎 Бонусные баллы: начислять % от оплаченного заказа</div>
      <div><label class="fld">Процент начисления, %</label><input class="field" id="loy-rate" type="number" value="${s.loyalty.rate_percent || 5}"></div>
      <div class="switch-row"><input type="checkbox" id="rev-auto" ${s.auto_approve_reviews ? 'checked' : ''}> Публиковать отзывы без модерации</div>
    </div>
    <div class="panel">
      <h3>Автоматика бота</h3>
      <div><label class="fld">Напоминание о неоплаченном заказе через, мин (0 = выкл.)</label><input class="field" id="ab-min" type="number" value="${s.abandoned_cart_minutes || 0}"></div>
      <div class="switch-row"><input type="checkbox" id="daily-en" ${s.daily_report ? 'checked' : ''}> Ежедневная сводка админу в Telegram</div>
      <div class="form-grid">
        <div><label class="fld">Час отправки сводки</label><input class="field" id="daily-hour" type="number" min="0" max="23" value="${s.daily_report_hour || 9}"></div>
        <div><label class="fld">Часовой пояс</label><input class="field" id="tz" value="${esc(s.timezone || 'Europe/Moscow')}"></div>
      </div>
      <h3>Полоса объявления и соцсети</h3>
      <div><label class="fld">Объявление над шапкой (пусто = выключено)</label><input class="field" id="ann" value="${esc(s.announcement || '')}" placeholder="🎉 Бесплатная доставка от 3000 ₽ + промокод SALE20"></div>
      <div class="form-grid">
        <div><label class="fld">Telegram (ссылка)</label><input class="field" id="so-tg-link" value="${esc((s.social_links || {}).tg || '')}" placeholder="https://t.me/..."></div>
        <div><label class="fld">VK</label><input class="field" id="so-vk-link" value="${esc((s.social_links || {}).vk || '')}" placeholder="https://vk.com/..."></div>
        <div><label class="fld">WhatsApp</label><input class="field" id="so-wa-link" value="${esc((s.social_links || {}).wa || '')}" placeholder="https://wa.me/7995..."></div>
        <div><label class="fld">Одноклассники</label><input class="field" id="so-ok-link" value="${esc((s.social_links || {}).ok || '')}" placeholder="https://ok.ru/..."></div>
      </div>
      <h3>Менеджер (кнопка «Связаться с менеджером»)</h3>
      <div class="form-grid">
        <div><label class="fld">Telegram-username менеджера (без @)</label><input class="field" id="mgr-user" value="${esc((s.manager || {}).username || '')}"></div>
        <div><label class="fld">Текст приветствия</label><input class="field" id="mgr-text" value="${esc((s.manager || {}).text || '')}"></div>
      </div>
      <h3>🤖 Искусственный интеллект</h3>
      <p class="hint">OpenAI-совместимый API: OpenAI, DeepSeek, OpenRouter и др. Используется для генерации
      описаний, SEO, рекламы и поиска аналогов (кнопки в карточке товара).</p>
      <div class="switch-row"><input type="checkbox" id="ai-en" ${s.ai.enabled ? 'checked' : ''}> Включить ИИ</div>
      <div class="form-grid">
        <div><label class="fld">API-ключ (пусто = не менять)</label><input class="field" id="ai-key" type="password" placeholder="••••••"></div>
        <div><label class="fld">Base URL</label><input class="field" id="ai-base" value="${esc(s.ai.base_url)}"></div>
        <div><label class="fld">Модель</label><input class="field" id="ai-model" value="${esc(s.ai.model)}"></div>
        <div><label class="fld">Tavily API-ключ (поиск аналогов в интернете)</label><input class="field" id="ai-tavily" type="password" placeholder="пусто = ссылки на маркетплейсы"></div>
      </div>
      <h3>📣 Автопостинг в соцсети</h3>
      <div class="switch-row"><input type="checkbox" id="so-auto" ${s.social.auto_post_new ? 'checked' : ''}> Автоматически публиковать новые товары</div>
      <div class="form-grid">
        <div><label class="fld">Telegram-канал (@channel или -100…)</label><input class="field" id="so-tg" value="${esc(s.social.telegram_channel)}"></div>
        <div><label class="fld">VK: access token (права wall, photos)</label><input class="field" id="so-vk" type="password" placeholder="пусто = не менять"></div>
        <div><label class="fld">VK: ID группы</label><input class="field" id="so-vkg" value="${esc(s.social.vk_group_id)}"></div>
        <div><label class="fld">Instagram: business user_id</label><input class="field" id="so-igu" value="${esc(s.social.instagram_user_id || '')}"></div>
        <div><label class="fld">Instagram: long-lived token (пусто = не менять)</label><input class="field" id="so-igt" type="password" placeholder="••••••"></div>
      </div>
      <h3>Avito — выкладывание объявлений</h3>
      <p class="hint">Два канала: REST API (создание/обновление/закрытие объявлений, нужна заявка на API
      в кабинете Avito) и <b>автозагрузка по XML-фиду</b> — ссылку ниже добавляете в Avito
      как источник автозагрузки, Avito сам забирает каталог по расписанию (API-заявка не нужна).</p>
      <div class="switch-row"><input type="checkbox" id="av-en" ${s.avito.enabled ? 'checked' : ''}> Включить выгрузку на Avito</div>
      <div class="switch-row"><input type="checkbox" id="av-auto" ${s.avito.auto_post_new ? 'checked' : ''}> Выкладывать новые товары автоматически</div>
      <div class="form-grid">
        <div><label class="fld">client_id (кабинет Avito → API)</label><input class="field" id="av-cid" value="${esc(s.avito.client_id)}"></div>
        <div><label class="fld">client_secret (пусто = не менять)</label><input class="field" id="av-secret" type="password" placeholder="••••••"></div>
        <div><label class="fld">Категория Avito (id)</label>
          <div style="display:flex;gap:8px">
            <input class="field" id="av-cat" type="number" value="${s.avito.category_id || 0}" style="margin:0">
            <button class="btn ghost small" onclick="loadAvitoCats()" type="button" style="white-space:nowrap">Категории</button>
          </div>
          <div id="av-cats" style="margin-top:6px"></div>
        </div>
        <div><label class="fld">Тип товара</label><select class="field" id="av-goods"><option ${s.avito.goods_type === 'Новое' ? 'selected' : ''}>Новое</option><option ${s.avito.goods_type === 'Б/у' ? 'selected' : ''}>Б/у</option></select></div>
        <div><label class="fld">Вид объявления</label><select class="field" id="av-adtype"><option ${s.avito.ad_type === 'Товар от производителя' ? 'selected' : ''}>Товар от производителя</option><option ${s.avito.ad_type === 'Товар от частного лица' ? 'selected' : ''}>Товар от частного лица</option></select></div>
        <div><label class="fld">Телефон для объявлений</label><input class="field" id="av-phone" value="${esc(s.avito.contact_phone)}"></div>
        <div><label class="fld">Адрес (город/улица)</label><input class="field" id="av-addr" value="${esc(s.avito.address)}" placeholder="Москва, ул. Примерная, 1"></div>
      </div>
      <label class="fld">Ссылка XML-фида автозагрузки (добавьте в кабинете Avito)</label>
      <input class="field" id="av-feed" value="${location.origin}/avito/autoload.xml?key=${esc(s.avito.feed_key || '')}" readonly style="font-family:monospace">
      <p class="hint">Фото в фиде появляются, когда задан публичный WEBAPP_URL в .env (Avito скачивает изображения
      по ссылке). При выкладке через API фото загружаются напрямую — публичный URL не обязателен.</p>
      <h3>FAQ (частые вопросы в боте)</h3>
      <div id="faq-rows"></div>
      <button class="btn ghost small" onclick="addFaqRow()">＋ Добавить вопрос</button>
    </div>
    <div class="panel">
      <h3>Оплата</h3>
      <label class="fld">Способ по умолчанию</label>
      <select class="field" id="pay-def">
        ${['test', 'yookassa', 'cryptobot', 'stars'].map(x => `<option value="${x}" ${s.payment_provider === x ? 'selected' : ''}>${x}</option>`).join('')}
      </select>
      <div class="switch-row"><input type="checkbox" id="pt-test" ${s.payments.test.enabled ? 'checked' : ''}> 💳 Тестовая оплата (имитация)</div>
      <div class="switch-row"><input type="checkbox" id="pt-tr" ${s.payments.transfer.enabled ? 'checked' : ''}> 💸 Перевод по СБП/карте (для продавцов-физлиц)</div>
      <div class="form-grid">
        <div><label class="fld">Телефон для СБП-перевода</label><input class="field" id="tr-phone" value="${esc(s.payments.transfer.phone)}" placeholder="+7 900 000-00-00"></div>
        <div><label class="fld">Номер карты</label><input class="field" id="tr-card" value="${esc(s.payments.transfer.card)}" placeholder="2202 20XX XXXX XXXX"></div>
        <div><label class="fld">Банк</label><input class="field" id="tr-bank" value="${esc(s.payments.transfer.bank)}"></div>
        <div><label class="fld">Получатель (ФИО)</label><input class="field" id="tr-name" value="${esc(s.payments.transfer.name)}"></div>
      </div>
      <p class="hint">Способ появится у покупателей, когда заполнены телефон или карта. Покупатель переводит деньги
      и нажимает «Я оплатил» — вам придёт уведомление, останется проверить поступление и подтвердить заказ.</p>
      <div class="switch-row"><input type="checkbox" id="pt-yk" ${s.payments.yookassa.enabled ? 'checked' : ''}> ЮKassa — карты РФ и СБП</div>
      <div class="form-grid">
        <div><label class="fld">shopId ЮKassa</label><input class="field" id="yk-shop" value="${esc(s.payments.yookassa.shop_id)}"></div>
        <div><label class="fld">Секретный ключ (пусто = не менять)</label><input class="field" id="yk-key" type="password" placeholder="••••••"></div>
      </div>
      <div class="switch-row"><input type="checkbox" id="pt-cb" ${s.payments.cryptobot.enabled ? 'checked' : ''}> 💎 CryptoBot — TON/USDT</div>
      <div class="form-grid">
        <div><label class="fld">Токен Crypto Pay (@CryptoBot)</label><input class="field" id="cb-token" type="password" placeholder="пусто = не менять"></div>
        <div><label class="fld">Актив</label><select class="field" id="cb-asset">${['USDT', 'TON', 'BTC', 'ETH'].map(a => `<option ${s.payments.cryptobot.asset === a ? 'selected' : ''}>${a}</option>`).join('')}</select></div>
      </div>
      <div class="switch-row"><input type="checkbox" id="pt-st" ${s.payments.stars.enabled ? 'checked' : ''}> ⭐ Telegram Stars</div>
      <div><label class="fld">Курс звёзд (звёзд за 1 ₽)</label><input class="field" id="st-rate" type="number" step="0.05" value="${s.payments.stars.rate}"></div>
      <div class="switch-row"><input type="checkbox" id="pt-tb" ${s.payments.tbank.enabled ? 'checked' : ''}> 🏦 Т-Банк — интернет-эквайринг (карты, СБП)</div>
      <div class="form-grid">
        <div><label class="fld">TerminalKey (ЛК Т-Бизнеса → Эквайринг)</label><input class="field" id="tb-key" value="${esc(s.payments.tbank.terminal_key)}" placeholder="…DEMO для тестов"></div>
        <div><label class="fld">Пароль терминала (пусто = не менять)</label><input class="field" id="tb-pass" type="password" placeholder="••••••"></div>
      </div>
    </div>
    <div class="panel">
      <h3>Тексты страниц сайта</h3>
      <label class="fld">О магазине</label><textarea class="field" id="tx-about">${esc(s.texts.about)}</textarea>
      <label class="fld">Доставка</label><textarea class="field" id="tx-delivery">${esc(s.texts.delivery)}</textarea>
      <label class="fld">Оплата</label><textarea class="field" id="tx-payments">${esc(s.texts.payments)}</textarea>
      <label class="fld">Контакты (футер)</label><textarea class="field" id="tx-contacts">${esc(s.texts.contacts)}</textarea>
    </div>
    <button class="btn" onclick="saveSettings()">💾 Сохранить настройки</button>`;

  renderDelRows();
  renderFaqRows();
}

function renderFaqRows() {
  const faq = SETTINGS.faq || [];
  $('#faq-rows').innerHTML = faq.map((f, i) => `
    <div class="del-row" style="align-items:flex-start">
      <input class="field w-label" value="${esc(f.q)}" placeholder="Вопрос" data-faq="${i}" data-f="q">
      <input class="field w-label" value="${esc(f.a)}" placeholder="Ответ" data-faq="${i}" data-f="a">
      <button class="btn danger small" onclick="delFaqRow(${i})">✕</button>
    </div>`).join('') || '<div class="hint">Вопросов пока нет</div>';
  document.querySelectorAll('#faq-rows [data-faq]').forEach(el => el.addEventListener('change', () => {
    const f = SETTINGS.faq[+el.dataset.faq];
    f[el.dataset.f] = el.value;
  }));
}

function addFaqRow() {
  SETTINGS.faq = SETTINGS.faq || [];
  SETTINGS.faq.push({ q: '', a: '' });
  renderFaqRows();
}
window.addFaqRow = addFaqRow;
function delFaqRow(i) { SETTINGS.faq.splice(i, 1); renderFaqRows(); }
window.delFaqRow = delFaqRow;

function renderDelRows() {
  $('#del-rows').innerHTML = Object.entries(SETTINGS.delivery).map(([id, d], i) => `
    <div class="del-row">
      <input class="field w-label" value="${esc(d.label)}" data-key="${id}" data-f="label">
      <input class="field w-price" type="number" value="${d.price}" data-key="${id}" data-f="price">
      <select class="field w-prov" data-key="${id}" data-f="provider">
        <option value="fixed" ${d.provider === 'fixed' ? 'selected' : ''}>фикс. цена</option>
        <option value="cdek" ${d.provider === 'cdek' ? 'selected' : ''}>СДЭК API</option>
        <option value="fivepost" ${d.provider === 'fivepost' ? 'selected' : ''}>5POST</option>
      </select>
      <button class="btn danger small" onclick="delRow('${id}')">✕</button>
    </div>`).join('');
  document.querySelectorAll('#del-rows [data-key]').forEach(el => el.addEventListener('change', () => {
    const d = SETTINGS.delivery[el.dataset.key];
    if (el.dataset.f === 'price') d.price = +el.value || 0;
    else d[el.dataset.f] = el.value;
  }));
}

function addDelRow() {
  const key = prompt('Ключ способа (латиницей), например: dpd');
  if (!key) return;
  SETTINGS.delivery[key] = { label: 'Новый способ', price: 0, provider: 'fixed' };
  renderDelRows();
}
window.addDelRow = addDelRow;
function delRow(key) { delete SETTINGS.delivery[key]; renderDelRows(); }
window.delRow = delRow;

async function saveSettings() {
  const patch = {
    shop_name: $('#st-name').value,
    currency: $('#st-curr').value,
    payment_provider: $('#pay-def').value,
    payments: {
      test: { enabled: $('#pt-test').checked },
      transfer: { enabled: $('#pt-tr').checked, phone: $('#tr-phone').value.trim(),
                  card: $('#tr-card').value.trim(), bank: $('#tr-bank').value.trim() || 'Сбербанк',
                  name: $('#tr-name').value.trim() },
      yookassa: { enabled: $('#pt-yk').checked, shop_id: $('#yk-shop').value.trim(), secret_key: $('#yk-key').value.trim() },
      cryptobot: { enabled: $('#pt-cb').checked, api_token: $('#cb-token').value.trim(), asset: $('#cb-asset').value },
      stars: { enabled: $('#pt-st').checked, rate: +$('#st-rate').value || 1 },
      tbank: { enabled: $('#pt-tb').checked, terminal_key: $('#tb-key').value.trim(), password: $('#tb-pass').value.trim() },
    },
    delivery: SETTINGS.delivery,
    cdek: { ...SETTINGS.cdek, enabled: $('#cdek-en').checked, account: $('#cdek-acc').value.trim(),
            password: $('#cdek-pass').value.trim(), from_city: +$('#cdek-from').value || 44 },
    fivepost: { ...SETTINGS.fivepost, enabled: $('#fp-en').checked, api_key: $('#fp-key').value.trim(),
                warehouse_id: $('#fp-wh').value.trim(), brand_name: $('#fp-brand').value.trim(),
                test_mode: $('#fp-test').checked },
    yandex: { ...SETTINGS.yandex, enabled: $('#yx-en').checked, token: $('#yx-token').value.trim(),
              warehouse_address: $('#yx-wh').value.trim(), test_mode: $('#yx-test').checked },
    free_delivery_from: +$('#free-from').value || 0,
    marketplace: { ...SETTINGS.marketplace, enabled: $('#mp-en').checked,
                   auto_approve_sellers: $('#mp-auto').checked,
                   commission_percent: +$('#mp-comm').value || 15 },
    smtp: { ...SETTINGS.smtp, enabled: $('#sm-en').checked, host: $('#sm-host').value.trim(),
            port: +$('#sm-port').value || 465, user: $('#sm-user').value.trim(),
            password: $('#sm-pass').value.trim(), from_email: $('#sm-from').value.trim() },
    loyalty: { ...SETTINGS.loyalty, enabled: $('#loy-en').checked, rate_percent: +$('#loy-rate').value || 0 },
    auto_approve_reviews: $('#rev-auto').checked,
    abandoned_cart_minutes: +$('#ab-min').value || 0,
    daily_report: $('#daily-en').checked,
    daily_report_hour: Math.min(23, Math.max(0, +$('#daily-hour').value || 9)),
    timezone: $('#tz').value.trim() || 'Europe/Moscow',
    announcement: $('#ann').value.trim(),
    social_links: { tg: $('#so-tg-link').value.trim(), vk: $('#so-vk-link').value.trim(),
                    wa: $('#so-wa-link').value.trim(), ok: $('#so-ok-link').value.trim() },
    manager: { username: $('#mgr-user').value.trim(), text: $('#mgr-text').value.trim() },
    faq: SETTINGS.faq || [],
    ai: { ...SETTINGS.ai, enabled: $('#ai-en').checked, api_key: $('#ai-key').value.trim(),
          base_url: $('#ai-base').value.trim() || 'https://api.openai.com/v1',
          model: $('#ai-model').value.trim() || 'gpt-4o-mini', tavily_key: $('#ai-tavily').value.trim() },
    social: { ...SETTINGS.social, auto_post_new: $('#so-auto').checked,
              telegram_channel: $('#so-tg').value.trim(), vk_token: $('#so-vk').value.trim(),
              vk_group_id: $('#so-vkg').value.trim(),
              instagram_user_id: $('#so-igu').value.trim(), instagram_token: $('#so-igt').value.trim() },
    avito: { ...SETTINGS.avito, enabled: $('#av-en').checked, auto_post_new: $('#av-auto').checked,
             client_id: $('#av-cid').value.trim(), client_secret: $('#av-secret').value.trim(),
             category_id: +$('#av-cat').value || 0, goods_type: $('#av-goods').value,
             ad_type: $('#av-adtype').value, contact_phone: $('#av-phone').value.trim(),
             address: $('#av-addr').value.trim() },
    texts: {
      about: $('#tx-about').value, delivery: $('#tx-delivery').value,
      payments: $('#tx-payments').value, contacts: $('#tx-contacts').value,
    },
  };
  try {
    SETTINGS = await api('/admin/api/settings', { method: 'PUT', body: JSON.stringify(patch) });
    toast('Настройки сохранены ✅');
  } catch (e) { toast(e.message, true); }
}
window.saveSettings = saveSettings;

/* ---------------- импорт и 1С ---------------- */
async function renderImport() {
  const s = await api('/admin/api/settings');
  $('#tab-import').innerHTML = `
    <h2>Импорт товаров и обмен с 1С</h2>
    <div class="panel">
      <h3>📊 Excel (.xlsx) — импорт и экспорт с фото</h3>
      <p class="hint">Импортируйте каталог из Excel: колонки <b>id, артикул, название, категория, цена,
      старая цена, остаток, в наличии, бейджи, описание, фото (url)</b> + столбец «фото»
      со встроенными картинками. Сначала скачайте экспорт как шаблон.</p>
      <div class="row-actions" style="flex-wrap:wrap">
        <button class="btn" onclick="exportXlsx()">⬇️ Экспорт в Excel (с фото)</button>
        <input class="field" type="file" id="xlsx-file" accept=".xlsx" style="flex:1; min-width:240px; margin:0">
        <button class="btn ghost" onclick="importXlsx()">📥 Импортировать Excel</button>
      </div>
      <div class="hint" id="xlsx-note" style="margin-top:8px"></div>
    </div>
    <div class="panel">
      <h3>📄 CSV</h3>
      <p class="hint">Колонки: <b>code, name, price, old_price, stock, description, category, photo_url, in_stock</b>.
      Сохраните Excel как «CSV UTF-8 (разделители — запятые или точка с запятой)».</p>
      <input class="field" type="file" id="csv-file" accept=".csv,.txt">
      <button class="btn" onclick="importCsv()">Импортировать CSV</button>
    </div>
    <div class="panel">
      <h3>🌐 YML-фид поставщика (Яндекс.Маркет)</h3>
      <p class="hint">Поддерживаются фиды YML от поставщиков и агрегаторов: карточки, цены, фото, категории.</p>
      <input class="field" id="yml-url" placeholder="https://поставщик.ru/feed.yml">
      <button class="btn" onclick="importYml()">Импортировать из фида</button>
    </div>
    <div class="panel">
      <h3>🔌 JSON API (любая система)</h3>
      <p class="hint">Любой источник: ваша ERP, парсер, агрегатор. Формат: {"products": [{"code","name","price","description","category","photo","photo_base64","in_stock"}]}</p>
      <textarea class="field" id="json-text" placeholder='{"products": [{"code": "A-1", "name": "Товар", "price": 990, "category": "Новое"}]}'></textarea>
      <button class="btn" onclick="importJson()">Импортировать JSON</button>
    </div>
    <div class="panel">
      <h3>1С — обмен данными</h3>
      <p class="hint">Расширение 1С (папка <b>1c-extension</b> в проекте) синхронизирует каталог и заказы с вашей базой.
      Токен доступа к API обмена:</p>
      <div style="display:flex; gap:10px; align-items:center">
        <input class="field" id="1c-token" value="${esc(s['1c_token'])}" readonly style="font-family:monospace">
        <button class="btn ghost" onclick="copyToken()">Копировать</button>
        <button class="btn danger small" onclick="resetToken()">Сбросить</button>
        <button class="btn" onclick="test1c()">🔌 Проверить связь с 1С</button>
      </div>
      <div class="hint" id="1c-test" style="margin-top:8px; line-height:1.7"></div>
      <h3>Эндпоинты обмена (заголовок X-1C-Token)</h3>
      <div class="hint" style="line-height:2">
        <b>GET /1c/catalog</b> — товары из магазина<br>
        <b>POST /1c/catalog</b> — выгрузка каталога из 1С в магазин<br>
        <b>GET /1c/orders?synced=0&status=paid,shipped</b> — новые заказы для 1С<br>
        <b>POST /1c/orders/ack</b> — подтверждение выгрузки {"ids": ["ORD-1001"]}<br>
        <b>POST /1c/orders/status</b> — статус из 1С {"id": "ORD-1001", "status": "shipped"}
      </div>
    </div>`;
}

async function importCsv() {
  const f = $('#csv-file').files[0];
  if (!f) return toast('Выберите файл CSV', true);
  const text = await f.text();
  runImport('csv', text);
}
window.importCsv = importCsv;
async function importYml() {
  const url = $('#yml-url').value.trim();
  if (!url) return toast('Введите URL фида', true);
  try {
    const r = await api('/admin/api/import/yml-url', { method: 'POST', body: JSON.stringify({ url }) });
    toast(`Импортировано: +${r.created}, обновлено: ${r.updated}`);
  } catch (e) { toast(e.message, true); }
}
window.importYml = importYml;
async function importJson() {
  const t = $('#json-text').value.trim();
  if (!t) return toast('Вставьте JSON', true);
  runImport('json', t);
}
window.importJson = importJson;
async function runImport(kind, data) {
  try {
    const r = await api('/admin/api/import', { method: 'POST', body: JSON.stringify({ type: kind, data }) });
    toast(`Готово: создано ${r.created}, обновлено ${r.updated}, пропущено ${r.skipped}`);
  } catch (e) { toast(e.message, true); }
}
function copyToken() {
  navigator.clipboard.writeText($('#1c-token').value);
  toast('Токен скопирован');
}
window.copyToken = copyToken;

async function test1c() {
  $('#1c-test').textContent = 'Проверяем…';
  try {
    const r = await api('/admin/api/1c/test');
    $('#1c-test').innerHTML =
      `<b>✅ Обмен с 1С работает.</b><br>` +
      `Каталог для 1С: <b>${r.products}</b> товаров · новых заказов для выгрузки: <b>${r.new_orders_for_1c}</b><br>` +
      `GET ${esc(r.endpoints.catalog)}<br>` +
      `GET ${esc(r.endpoints.orders)}<br>` +
      `Заголовок: <code>X-1C-Token: ${esc(r.token.slice(0, 10))}…</code>`;
  } catch (e) {
    $('#1c-test').innerHTML = '❌ ' + esc(e.message);
  }
}
window.test1c = test1c;

async function exportXlsx() {
  try {
    const res = await fetch('/admin/api/export/products.xlsx', { headers: { 'X-Admin-Token': TOKEN } });
    if (!res.ok) throw new Error('Ошибка экспорта');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'products.xlsx';
    a.click();
    toast('Excel с фото скачан ✅');
  } catch (e) { toast(e.message, true); }
}
window.exportXlsx = exportXlsx;

async function importXlsx() {
  const f = $('#xlsx-file').files[0];
  if (!f) return toast('Выберите файл .xlsx', true);
  const fd = new FormData();
  fd.append('file', f);
  $('#xlsx-note').textContent = 'Импортируем…';
  try {
    const res = await fetch('/admin/api/import/xlsx', {
      method: 'POST', headers: { 'X-Admin-Token': TOKEN }, body: fd,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка импорта');
    $('#xlsx-note').textContent = `✅ Готово: создано ${data.created}, обновлено ${data.updated}, пропущено ${data.skipped}`;
    toast('Импорт из Excel завершён');
    renderProducts();
  } catch (e) {
    $('#xlsx-note').textContent = '❌ ' + e.message;
    toast(e.message, true);
  }
}
window.importXlsx = importXlsx;
async function resetToken() {
  if (!confirm('Сбросить токен 1С? Старый перестанет работать.')) return;
  const r = await api('/admin/api/1c/reset-token', { method: 'POST', body: '{}' });
  $('#1c-token').value = r['1c_token'];
  toast('Токен обновлён');
}
window.resetToken = resetToken;

/* ---------------- каталог: подкатегории и SEO ---------------- */
async function renderCatalogTab() {
  const d = await api('/admin/api/subs');
  const subs = d.subs || [];
  const cats = d.categories || [];
  const real = subs.filter(s => s.id);
  const auto = subs.filter(s => !s.id);
  $('#tab-catalog').innerHTML = `
    <h2>Подкатегории каталога <span class="hint">(ЧПУ-адреса и SEO-тексты)</span></h2>
    <div class="panel">
      <h3>➕ Добавить подкатегорию</h3>
      <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end">
        <div><label class="fld">Категория</label><input class="field" id="sc-cat" list="sc-cats" placeholder="Обувь" style="margin:0"></div>
        <datalist id="sc-cats">${cats.map(c => `<option value="${esc(c)}">`).join('')}</datalist>
        <div><label class="fld">Подкатегория</label><input class="field" id="sc-sub" placeholder="Кроссовки" style="margin:0"></div>
        <div><label class="fld">Slug (пусто = авто)</label><input class="field" id="sc-slug" placeholder="krossovki" style="margin:0"></div>
        <div><label class="fld">SEO-заголовок</label><input class="field" id="sc-title" placeholder="Кроссовки — купить с доставкой" style="min-width:280px; margin:0"></div>
        <button class="btn" onclick="addSub()">Сохранить</button>
      </div>
      <div class="full"><label class="fld">SEO-текст (описание страницы)</label><textarea class="field" id="sc-text" placeholder="Кроссовки б/у и новые: Nike, Adidas…"></textarea></div>
    </div>
    <div class="panel" style="padding:0">
      <table class="table">
        <tr><th>Категория</th><th>Подкатегория</th><th>Slug (ЧПУ)</th><th>SEO-заголовок</th><th>Ссылка</th><th></th></tr>
        ${real.map(s => `<tr>
          <td>${esc(s.category)}</td><td><b>${esc(s.subcategory)}</b></td>
          <td><input class="field" id="sub-slug-${s.id}" value="${esc(s.slug)}" style="margin:0"></td>
          <td><input class="field" id="sub-title-${s.id}" value="${esc(s.seo_title)}" style="margin:0"></td>
          <td><a class="btn ghost small" href="/catalog/${esc(s.cat_slug || '')}/${esc(s.slug)}" target="_blank">Открыть</a></td>
          <td><button class="btn ghost small" onclick="updateSub(${s.id}, '${esc(s.category)}', '${esc(s.subcategory)}')">💾</button>
              <button class="btn danger small" onclick="delSub(${s.id})">✕</button></td></tr>`).join('') || '<tr><td colspan="6" class="hint">Подкатегорий пока нет — добавьте первую</td></tr>'}
      </table>
      ${auto.length ? `<p class="hint">Из товаров (без SEO-настроек): ${auto.map(s => esc(s.category + ' / ' + s.subcategory)).join(', ')}</p>` : ''}
    </div>`;
}
async function addSub() {
  try {
    await api('/admin/api/subs', { method: 'POST', body: JSON.stringify({
      category: $('#sc-cat').value, subcategory: $('#sc-sub').value,
      slug: $('#sc-slug').value, seo_title: $('#sc-title').value, seo_text: $('#sc-text').value,
    }) });
    toast('Подкатегория сохранена ✅');
    renderCatalogTab();
  } catch (e) { toast(e.message, true); }
}
window.addSub = addSub;
async function updateSub(id, category, subcategory) {
  try {
    await api('/admin/api/subs', { method: 'POST', body: JSON.stringify({
      id: id, category: category, subcategory: subcategory,
      slug: $('#sub-slug-' + id).value, seo_title: $('#sub-title-' + id).value,
    }) });
    toast('Сохранено ✅');
  } catch (e) { toast(e.message, true); }
}
window.updateSub = updateSub;
async function delSub(id) {
  if (!confirm('Удалить подкатегорию?')) return;
  try { await api('/admin/api/subs/' + id, { method: 'DELETE' }); toast('Удалена'); renderCatalogTab(); }
  catch (e) { toast(e.message, true); }
}
window.delSub = delSub;

/* ---------------- тарифы (настраиваемые администратором) ---------------- */
async function renderTariffs() {
  let t = {};
  try { t = await api('/admin/api/tariffs'); } catch (e) { /* значения по умолчанию ниже */ }
  window.TARIFFS = t;
  const plans = t.seller_plans || [];
  const wh = t.warehouse_plans || [];
  const ps = t.promo_services || {};
  const planRow = (p, prefix, extra) => `
    <tr>
      <td><input class="field" data-t="${prefix}.${p.id}.name" value="${esc(p.name)}" style="margin:0"></td>
      <td><input class="field" data-t="${prefix}.${p.id}.price" type="number" value="${p.price}" style="width:90px; margin:0"></td>
      ${extra.map(f => `<td><input class="field" data-t="${prefix}.${p.id}.${f.key}" type="number" value="${p[f.key] ?? 0}" style="width:80px; margin:0"></td>`).join('')}
    </tr>`;
  $('#tab-tariffs').innerHTML = `
    <h2>Тарифы и лимиты <span class="hint">— всё настраивается здесь, применяется сразу</span></h2>
    <div class="panel">
      <h3>⚙️ Основные параметры</h3>
      <div style="display:flex; gap:14px; flex-wrap:wrap; align-items:flex-end">
        <div><label class="fld">Лимиты включены</label>
          <select class="field" id="t-enabled" style="margin:0"><option value="1" ${t.enabled ? 'selected' : ''}>Да</option><option value="0" ${!t.enabled ? 'selected' : ''}>Нет</option></select></div>
        <div><label class="fld">Базовая комиссия, %</label><input class="field" id="t-commission" type="number" value="${t.commission_percent ?? 15}" style="width:90px; margin:0"></div>
        <div><label class="fld">Холд средств (эскроу), дней</label><input class="field" id="t-escrow" type="number" value="${t.escrow_days ?? 7}" style="width:90px; margin:0"></div>
        <div><label class="fld">Тариф по умолчанию</label>
          <select class="field" id="t-default" style="margin:0">${plans.map(p => `<option value="${p.id}" ${(t.seller_default_plan || 'start') === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></div>
      </div>
    </div>
    <div class="panel" style="padding:0">
      <h3>🏪 Тарифы продавцов маркетплейса</h3>
      <table class="table">
        <tr><th>Название</th><th>Цена ₽/мес</th><th>Объявлений</th><th>Фото</th><th>ИИ/мес</th><th>Поднятий</th><th>VIP</th><th>Промокоды</th><th>Скидка комиссии</th></tr>
        ${plans.map(p => planRow(p, 'seller_plans', [
          { key: 'max_products' }, { key: 'max_photos' }, { key: 'ai_month' },
          { key: 'boost_month' }, { key: 'vip_products' }, { key: 'promos_max' },
          { key: 'commission_discount' },
        ])).join('')}
      </table>
    </div>
    <div class="panel" style="padding:0">
      <h3>📦 Тарифы приложения «Склад»</h3>
      <table class="table">
        <tr><th>Название</th><th>Цена ₽/мес</th><th>Позиций</th><th>Пользователей</th><th>ИИ/мес</th></tr>
        ${wh.map(p => planRow(p, 'warehouse_plans', [
          { key: 'max_positions' }, { key: 'max_users' }, { key: 'ai_month' },
        ])).join('')}
      </table>
    </div>
    <div class="panel">
      <h3>📣 Услуги продвижения (₽)</h3>
      <div style="display:flex; gap:14px; flex-wrap:wrap; align-items:flex-end">
        <div><label class="fld">Поднять — 1 день</label><input class="field" id="t-boost1d" type="number" value="${ps.boost_1d ?? 49}" style="width:90px; margin:0"></div>
        <div><label class="fld">Поднять — 3 дня</label><input class="field" id="t-boost3d" type="number" value="${ps.boost_3d ?? 99}" style="width:90px; margin:0"></div>
        <div><label class="fld">Поднять — 7 дней</label><input class="field" id="t-boost7d" type="number" value="${ps.boost_7d ?? 199}" style="width:90px; margin:0"></div>
        <div><label class="fld">VIP-карточка — неделя</label><input class="field" id="t-vipweek" type="number" value="${ps.vip_week ?? 149}" style="width:90px; margin:0"></div>
        <div><label class="fld">ИИ-пакет — 20 генераций</label><input class="field" id="t-aipack" type="number" value="${ps.ai_pack_20 ?? 99}" style="width:90px; margin:0"></div>
      </div>
    </div>
    <button class="btn primary" onclick="saveTariffs()">💾 Сохранить тарифы</button>
    <p class="hint">Лимиты применяются сразу: продавцам при создании объявлений/промокодов и генерациях ИИ.
    Комиссия пересчитывается для новых заказов. Холд средств — дни до разморозки после оплаты.</p>`;
}
async function saveTariffs() {
  const val = (sel, num) => num ? (+$(sel).value || 0) : $(sel).value;
  const t = window.TARIFFS || {};
  const plans = t.seller_plans || [];
  const wh = t.warehouse_plans || [];
  const getPlans = (list, prefix, keys) => list.map(p => {
    const o = { ...p };
    document.querySelectorAll(`[data-t^="${prefix}.${p.id}."]`).forEach(inp => {
      const key = inp.dataset.t.split('.').slice(2).join('.');
      const v = inp.value;
      o[key] = (key === 'name') ? v : (v === '' ? 0 : +v);
    });
    return o;
  });
  const body = {
    enabled: $('#t-enabled').value === '1',
    commission_percent: +$('#t-commission').value || 15,
    escrow_days: +$('#t-escrow').value || 0,
    seller_default_plan: $('#t-default').value,
    seller_plans: getPlans(plans, 'seller_plans'),
    warehouse_plans: getPlans(wh, 'warehouse_plans'),
    promo_services: {
      boost_1d: +$('#t-boost1d').value || 0, boost_3d: +$('#t-boost3d').value || 0,
      boost_7d: +$('#t-boost7d').value || 0, vip_week: +$('#t-vipweek').value || 0,
      ai_pack_20: +$('#t-aipack').value || 0,
    },
  };
  try {
    await api('/admin/api/tariffs', { method: 'PUT', body: JSON.stringify(body) });
    toast('Тарифы сохранены ✅');
    renderTariffs();
    renderSellers();
  } catch (e) { toast(e.message, true); }
}
window.saveTariffs = saveTariffs;

/* ---------------- старт ---------------- */
const RENDERERS = {
  dashboard: renderDashboard, products: renderProducts, catalog: renderCatalogTab,
  orders: renderOrders, sellers: renderSellers, tariffs: renderTariffs,
  promos: renderPromos, reviews: renderReviews, blog: renderBlog,
  broadcast: renderBroadcast, reports: renderReports, settings: renderSettings,
  import: renderImport,
};

async function init() {
  if (!TOKEN) { showLogin(); return; }
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  try {
    const cfg = await api('/api/config');
    $('#sb-name').textContent = cfg.shop_name;
  } catch (e) { showLogin(); return; }
  try { window.TARIFFS = await api('/admin/api/tariffs'); } catch (e) { window.TARIFFS = {}; }
  for (const [tab, fn] of Object.entries(RENDERERS)) {
    try { await fn(); } catch (e) { $('#' + 'tab-' + tab).innerHTML = '<div class="panel err">' + esc(e.message) + '</div>'; }
  }
}
init();
