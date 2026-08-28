'use strict';
/* Кабинет продавца маркетплейса */
const $ = (sel, el) => (el || document).querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => new Intl.NumberFormat('ru-RU').format(n) + ' ₽';

const STATUS = {
  pending_payment: '⏳ ожидает оплаты', paid: '✅ оплачен', processing: '🔧 в обработке',
  shipped: '🚚 отправлен', delivered: '🎉 доставлен', cancelled: '❌ отменён',
};

let KEY = localStorage.getItem('tgshop_seller_key') || '';
let ME = null;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', 'X-Seller-Key': KEY, ...(opts.headers || {}) },
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

function showLogin() { $('#login').classList.remove('hidden'); $('#app').classList.add('hidden'); }

async function doLogin(inputKey) {
  const err = $('#login-err');
  err.classList.add('hidden');
  const k = (inputKey || $('#key').value || '').trim();
  if (!k) { err.textContent = 'Введите ключ'; err.classList.remove('hidden'); return; }
  KEY = k;
  try {
    ME = await api('/api/seller/me');
    localStorage.setItem('tgshop_seller_key', KEY);
    $('#login').classList.add('hidden');
    $('#app').classList.remove('hidden');
    init();
  } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); }
}
function logout() { localStorage.removeItem('tgshop_seller_key'); KEY = ''; ME = null; showLogin(); }

document.querySelectorAll('.side nav button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.side nav button').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  document.querySelectorAll('.tab').forEach(t => t.classList.add('hidden'));
  $('#tab-' + b.dataset.tab).classList.remove('hidden');
}));

/* ---------------- кабинет ---------------- */
async function renderDashboard() {
  ME = await api('/api/seller/me');
  const st = ME.stats;
  const mp = ME.marketplace;
  const lm = ME.limits || {};
  const plan = lm.plan || {};
  const ver = ME.verification || {};
  const vLabel = ver.status === 'verified' ? '✅ Проверенный продавец'
    : ver.status === 'pending' ? '⏳ Документы на проверке'
    : ver.status === 'rejected' ? '❌ Верификация отклонена — подайте повторно' : '⚪ Не верифицирован';
  const pct = (a, b) => b > 0 ? Math.min(100, Math.round(a / b * 100)) : 0;
  const bar = (a, b) => `<div style="background:#eee;border-radius:6px;height:8px;margin-top:4px"><div style="background:#0F766E;width:${pct(a, b)}%;height:8px;border-radius:6px"></div></div>`;
  const verBlock = ver.status !== 'verified' ? `
    <div class="panel">
      <h3>🛡 Верификация витрины ${vLabel}</h3>
      ${ver.status === 'pending' ? '<p class="hint">Документы отправлены — администратор проверит их в течение дня.</p>'
        : `<p class="hint">Подтвердите себя как продавца: покупатели больше доверяют проверенным витринам (значок ✅ на витрине).</p>
        <div style="display:flex; gap:10px; flex-wrap:wrap">
          <input class="field" id="vf-inn" placeholder="ИНН (10–12 цифр)" style="margin:0; max-width:200px">
          <input class="field" id="vf-owner" placeholder="ФИО владельца" style="margin:0; max-width:260px">
          <button class="btn" onclick="submitVerify()">Отправить на проверку</button>
        </div>`}
    </div>` : '';
  $('#tab-dashboard').innerHTML = `
    <h2>${esc(ME.store_name)}</h2>
    <div class="cards">
      <div class="stat"><div class="v">${st.products}</div><div class="l">Моих товаров</div></div>
      <div class="stat"><div class="v">${st.orders}</div><div class="l">Заказов</div></div>
      <div class="stat"><div class="v">${fmt(st.sales)}</div><div class="l">Продаж всего</div></div>
      <div class="stat"><div class="v">${fmt(st.balance)}</div><div class="l">Баланс к выплате${ME.held_balance ? `<div class="hint">🔒 в холде: ${fmt(ME.held_balance)}</div>` : ''}</div></div>
    </div>
    <div class="panel">
      <h3>📈 Мой тариф: ${esc(plan.name || 'Старт')} ${plan.price ? `· <b>${fmt(plan.price)}/мес</b>` : '· бесплатно'}</h3>
      <div class="form-grid" style="margin-top:6px">
        <div><label class="fld">Объявления: ${lm.used_products} / ${lm.max_products}</label>${bar(lm.used_products, lm.max_products)}</div>
        <div><label class="fld">ИИ-генерации: ${lm.ai_month < 0 ? 'без лимита' : `${lm.ai_used} / ${lm.ai_month} в этом месяце`}</label>${lm.ai_month < 0 ? '' : bar(lm.ai_used, lm.ai_month)}</div>
        <div><label class="fld">Фото на товар: до ${lm.max_photos}</label></div>
        <div><label class="fld">Промокоды: ${lm.promos_max < 0 ? 'без лимита' : `до ${lm.promos_max}`}</label></div>
      </div>
      <p class="hint" style="margin-top:10px">Сменить тариф: <button class="btn ghost small" onclick="requestPlan('${esc(plan.id || 'start')}')">Запросить смену</button> — администратор подтвердит запрос.</p>
    </div>
    <div class="panel">
      <h3>Условия площадки</h3>
      <p class="hint">Комиссия: <b>${lm.commission ?? (ME.commission_percent || mp.commission_percent || 15)}%</b> с продажи
      (остальное — на ваш баланс). Оплату и доставку для покупателей обеспечивает площадка.
      ${lm.escrow_days ? `<br>Средства зачисляются в холд и размораживаются через <b>${lm.escrow_days} дн.</b> после оплаты.` : ''}</p>
      <p class="hint">Статус витрины: <b>${ME.status === 'active' ? '✅ активна' : ME.status === 'pending' ? '⏳ на подтверждении' : '⛔ заблокирована'}</b> · ${vLabel}</p>
      <p class="hint">Ваша витрина: <a href="/seller/${esc(ME.slug)}" target="_blank">/seller/${esc(ME.slug)}</a></p>
    </div>
    ${verBlock}`;
}
async function submitVerify() {
  try {
    await api('/api/seller/verify', { method: 'POST', body: JSON.stringify({
      inn: $('#vf-inn').value.trim(), owner_name: $('#vf-owner').value.trim(),
    }) });
    toast('Документы отправлены на проверку ✅');
    renderDashboard();
  } catch (e) { toast(e.message, true); }
}
window.submitVerify = submitVerify;
async function requestPlan(current) {
  const plans = ME.plans || [];
  const names = plans.map((p, i) => `${i + 1}. ${p.name} — ${p.price ? fmt(p.price) + '/мес' : 'бесплатно'}`).join('\n');
  const choice = prompt('Тарифы площадки:\n\n' + names + '\n\nВведите номер тарифа:', '');
  const idx = parseInt(choice, 10);
  if (!idx || !plans[idx - 1]) { if (choice !== null) toast('Неверный номер', true); return; }
  if (plans[idx - 1].id === current) { toast('У вас уже этот тариф'); return; }
  try {
    const r = await api('/api/seller/plan/request', { method: 'POST', body: JSON.stringify({ plan_id: plans[idx - 1].id }) });
    toast(r.message);
  } catch (e) { toast(e.message, true); }
}
window.requestPlan = requestPlan;

/* ---------------- чат с покупателями ---------------- */
let CHAT_THREAD = null;   // {product_id, buyer_key, seller_id}
let CHAT_TITLE = '';
let CHAT_POLL = null;
async function renderChat() {
  const d = await api('/api/chat/threads');
  const th = d.threads || [];
  $('#tab-chat').innerHTML = `
    <h2>Сообщения от покупателей <span class="hint">(${th.length})</span></h2>
    <div style="display:flex; gap:14px; align-items:flex-start; flex-wrap:wrap">
      <div class="panel" style="padding:0; flex:1; min-width:260px">
        ${th.length ? th.map(t => `
          <div class="chat-th" style="padding:12px 14px; border-bottom:1px solid #eee; cursor:pointer; display:flex; gap:10px; align-items:center"
               onclick="openChatThread(${t.product_id}, ${t.seller_id}, '${esc(t.buyer_key)}', '${esc(t.product_name)} · ${esc(t.buyer_name || 'Покупатель')}')">
            <img src="${esc(t.product_photo)}" style="width:42px;height:42px;border-radius:8px;object-fit:cover" alt="">
            <div style="flex:1; min-width:0">
              <b>${esc(t.product_name)}</b><br>
              <span class="hint">${esc(t.buyer_name || 'Покупатель')} · ${esc(t.last_text || '').slice(0, 60)}</span>
            </div>
            ${t.unread ? `<span style="background:#0F766E;color:#fff;border-radius:12px;padding:2px 8px;font-size:12px">${t.unread}</span>` : ''}
          </div>`).join('') : '<div class="hint" style="padding:14px">Сообщений пока нет. Покупатели пишут через кнопку «Спросить продавца» на товаре.</div>'}
      </div>
      <div class="panel" id="chat-win" style="flex:2; min-width:300px; display:${CHAT_THREAD ? 'block' : 'none'}">
        <h3 id="chat-title"></h3>
        <div id="chat-msgs" style="max-height:420px; overflow-y:auto; display:flex; flex-direction:column; gap:8px"></div>
        <div style="display:flex; gap:8px; margin-top:10px">
          <input class="field" id="chat-input" placeholder="Ваш ответ…" style="margin:0" onkeydown="if(event.key==='Enter')sendChatMsg()">
          <button class="btn" onclick="sendChatMsg()">Отправить</button>
        </div>
      </div>
    </div>`;
  if (CHAT_THREAD) {
    $('#chat-title').textContent = CHAT_TITLE;
    await loadChatMessages();
  }
  startChatPoll();
}
async function openChatThread(productId, sellerId, buyerKey, title) {
  CHAT_THREAD = { product_id: productId, seller_id: sellerId, buyer_key: buyerKey };
  CHAT_TITLE = title;
  await renderChat();
}
window.openChatThread = openChatThread;
async function loadChatMessages() {
  if (!CHAT_THREAD) return;
  const ms = await api('/api/chat/messages?product_id=' + CHAT_THREAD.product_id +
    '&seller_id=' + CHAT_THREAD.seller_id + '&buyer_key=' + encodeURIComponent(CHAT_THREAD.buyer_key));
  $('#chat-msgs').innerHTML = ms.map(m => `
    <div style="align-self:${m.sender === 'seller' ? 'flex-end' : 'flex-start'}; max-width:75%;
      background:${m.sender === 'seller' ? '#0F766E' : '#f0f0f0'}; color:${m.sender === 'seller' ? '#fff' : '#111'};
      padding:8px 12px; border-radius:12px; font-size:14px">
      ${esc(m.text)}<div style="font-size:10px; opacity:.7; margin-top:3px">${m.ts.slice(11, 16)}</div>
    </div>`).join('') || '<div class="hint">Начните диалог</div>';
  $('#chat-msgs').scrollTop = 99999;
}
async function sendChatMsg() {
  const text = $('#chat-input').value.trim();
  if (!text || !CHAT_THREAD) return;
  try {
    await api('/api/chat/send', { method: 'POST', body: JSON.stringify({ ...CHAT_THREAD, text }) });
    $('#chat-input').value = '';
    await loadChatMessages();
  } catch (e) { toast(e.message, true); }
}
window.sendChatMsg = sendChatMsg;
async function startChatPoll() {
  if (CHAT_POLL) clearInterval(CHAT_POLL);
  CHAT_POLL = setInterval(async () => {
    try {
      const d = await api('/api/chat/unread');
      const badge = $('#chat-badge');
      if (d.unread > 0) {
        if (badge) badge.textContent = d.unread;
        else {
          const b = document.querySelector('[data-tab="chat"]');
          const s = document.createElement('span');
          s.id = 'chat-badge';
          s.style.cssText = 'background:#e74c3c;color:#fff;border-radius:10px;padding:1px 7px;font-size:11px;margin-left:6px';
          b.appendChild(s);
          s.textContent = d.unread;
        }
        if (document.querySelector('#tab-chat').classList.contains('hidden') === false) renderChat();
      } else if (badge) badge.remove();
    } catch (e) { /* сессия истекла — останавливаем */ clearInterval(CHAT_POLL); }
  }, 15000);
}

/* ---------------- товары ---------------- */
async function renderProducts() {
  const ps = await api('/api/seller/products');
  $('#tab-products').innerHTML = `
    <h2>Мои товары <span class="hint">(${ps.length})</span></h2>
    <button class="btn" onclick="openProductModal()">➕ Добавить товар</button>
    <div class="panel" style="margin-top:14px; padding:0">
      <table class="table">
        <tr><th></th><th>Название</th><th>Цена</th><th>Остаток</th><th>В наличии</th><th></th></tr>
        ${ps.map(p => `<tr>
          <td><img src="${esc(p.photo)}" alt=""></td>
          <td>${esc(p.name)}${p.old_price > p.price ? `<br><span class="hint"><s>${fmt(p.old_price)}</s> → ${fmt(p.price)}</span>` : ''}</td>
          <td><b>${fmt(p.price)}</b></td>
          <td>${p.stock < 0 ? '∞' : p.stock}</td>
          <td>${p.in_stock ? '✅' : '❌'}</td>
          <td class="row-actions">
            <button class="btn ghost small" onclick='openProductModal(${JSON.stringify(p).replace(/'/g, "&#39;")})'>Изменить</button>
            <button class="btn danger small" onclick="delProduct(${p.id})">Удалить</button>
          </td></tr>`).join('') || '<tr><td colspan="6" class="hint">Товаров нет — добавьте первый!</td></tr>'}
      </table>
    </div>`;
}

function openProductModal(p) {
  p = p || {};
  const m = document.createElement('div');
  m.className = 'modal-overlay';
  m.innerHTML = `
    <div class="modal">
      <h2>${p.id ? 'Изменить товар' : 'Новый товар'}</h2>
      <div class="form-grid">
        <div class="full"><label class="fld">Название *</label><input class="field" id="pf-name" value="${esc(p.name || '')}"></div>
        <div><label class="fld">Цена, ₽ *</label><input class="field" id="pf-price" type="number" value="${p.price ?? ''}"></div>
        <div><label class="fld">Старая цена (для скидки)</label><input class="field" id="pf-old" type="number" value="${p.old_price ?? 0}"></div>
        <div><label class="fld">Категория</label><input class="field" id="pf-cat" value="${esc(p.category || '')}"></div>
        <div><label class="fld">Подкатегория</label><input class="field" id="pf-subcat" value="${esc(p.subcategory || '')}" placeholder="например: Кроссовки"></div>
        <div><label class="fld">Состояние</label><select class="field" id="pf-cond">
          <option value="new" ${p.condition !== 'used' && p.condition !== 'defect' ? 'selected' : ''}>✦ Новое</option>
          <option value="used" ${p.condition === 'used' ? 'selected' : ''}>↻ Б/у</option>
          <option value="defect" ${p.condition === 'defect' ? 'selected' : ''}>⚠ С дефектами</option>
        </select></div>
        <div><label class="fld">Остаток (пусто = ∞)</label><input class="field" id="pf-stock" type="number" value="${p.stock ?? ''}"></div>
        <div class="full"><label class="fld">Описание</label><textarea class="field" id="pf-desc">${esc(p.description || '')}</textarea></div>
        <div class="full"><label class="fld">Фото (файл)</label><input class="field" type="file" id="pf-file" accept="image/*"></div>
        <div class="full">
          <label class="fld">Параметры (бренд, размер, цвет…)</label>
          <div id="pf-params"></div>
          <button type="button" class="btn ghost small" onclick="addParamRow()">＋ Добавить параметр</button>
        </div>
        <label class="switch-row full"><input type="checkbox" id="pf-on" ${p.in_stock !== false ? 'checked' : ''}> В наличии</label>
      </div>
      <div style="display:flex; gap:10px; margin-top:14px">
        <button class="btn" id="pf-save">Сохранить</button>
        <button class="btn ghost" onclick="this.closest('.modal-overlay').remove()">Отмена</button>
      </div>
    </div>`;
  document.body.appendChild(m);
  Object.entries(p.params || {}).forEach(([k, v]) => addParamRow(k, v));
  $('#pf-save').addEventListener('click', async () => {
    const file = $('#pf-file').files[0];
    let photoData = '';
    if (file) {
      photoData = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(file); });
    }
    const params = {};
    document.querySelectorAll('#pf-params [data-pk]').forEach(inp => {
      const k = inp.value.trim();
      const v = (inp.nextElementSibling ? inp.nextElementSibling.value : '').trim();
      if (k && v) params[k] = v;
    });
    const body = {
      name: $('#pf-name').value, price: +$('#pf-price').value, old_price: +$('#pf-old').value || 0,
      stock: $('#pf-stock').value === '' ? -1 : +$('#pf-stock').value,
      category: $('#pf-cat').value || 'Прочее', subcategory: $('#pf-subcat').value,
      condition: $('#pf-cond').value, params,
      description: $('#pf-desc').value,
      in_stock: $('#pf-on').checked, photo_data: photoData,
    };
    try {
      if (p.id) await api('/api/seller/products/' + p.id, { method: 'PUT', body: JSON.stringify(body) });
      else await api('/api/seller/products', { method: 'POST', body: JSON.stringify(body) });
      toast('Сохранено ✅');
      m.remove(); renderProducts(); renderDashboard();
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
  try { await api('/api/seller/products/' + id, { method: 'DELETE' }); toast('Удалён'); renderProducts(); }
  catch (e) { toast(e.message, true); }
}
window.delProduct = delProduct;

/* ---------------- акции ---------------- */
async function renderPromos() {
  const ps = await api('/api/seller/promos');
  $('#tab-promos').innerHTML = `
    <h2>Мои промокоды</h2>
    <div class="panel">
      <h3>Создать промокод (действует только на ваши товары)</h3>
      <div class="form-grid">
        <div><label class="fld">Код</label><input class="field" id="pr-code" placeholder="MYSTORE10"></div>
        <div><label class="fld">Тип</label><select class="field" id="pr-type"><option value="percent">Процент (%)</option><option value="fixed">Фикс. сумма (₽)</option></select></div>
        <div><label class="fld">Значение</label><input class="field" id="pr-value" type="number" value="10"></div>
        <div><label class="fld">Лимит использований (0 = без)</label><input class="field" id="pr-max" type="number" value="0"></div>
        <div><label class="fld">Действует до</label><input class="field" id="pr-exp" type="date"></div>
        <div class="full"><label class="fld">Описание</label><input class="field" id="pr-desc"></div>
      </div>
      <button class="btn" onclick="createPromo()">➕ Создать</button>
    </div>
    <div class="panel" style="padding:0">
      <table class="table">
        <tr><th>Код</th><th>Тип</th><th>Значение</th><th>Использовано</th><th>Лимит</th><th>До</th><th></th></tr>
        ${ps.map(x => `<tr><td><b>${esc(x.code)}</b><br><span class="hint">${esc(x.description || '')}</span></td>
          <td>${x.type === 'percent' ? '%' : '₽'}</td><td>${x.value}</td><td>${x.used}</td>
          <td>${x.max_uses || '∞'}</td><td class="hint">${esc(x.expires_at || '—')}</td>
          <td><button class="btn danger small" onclick="delPromo('${esc(x.code)}')">✕</button></td></tr>`).join('') || '<tr><td colspan="7" class="hint">Промокодов нет</td></tr>'}
      </table>
    </div>`;
}
async function createPromo() {
  try {
    await api('/api/seller/promos', { method: 'POST', body: JSON.stringify({
      code: $('#pr-code').value, type: $('#pr-type').value, value: +$('#pr-value').value,
      max_uses: +$('#pr-max').value || 0, expires_at: $('#pr-exp').value, description: $('#pr-desc').value, enabled: true,
    }) });
    toast('Промокод создан ✅'); renderPromos();
  } catch (e) { toast(e.message, true); }
}
window.createPromo = createPromo;
async function delPromo(code) {
  if (!confirm('Удалить ' + code + '?')) return;
  try { await api('/api/seller/promos/' + code, { method: 'DELETE' }); toast('Удалён'); renderPromos(); }
  catch (e) { toast(e.message, true); }
}
window.delPromo = delPromo;

/* ---------------- заказы ---------------- */
async function renderOrders() {
  const orders = await api('/api/seller/orders');
  $('#tab-orders').innerHTML = `
    <h2>Мои заказы</h2>
    ${orders.map(o => {
      const mine = o.items.filter(i => i.seller_id === ME.id);
      const sum = mine.reduce((s, i) => s + i.price * i.qty, 0);
      return `<div class="panel">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px">
          <b>${esc(o.id)}</b><span>${STATUS[o.status] || esc(o.status)}</span>
          <b>${fmt(sum)}</b>
          <span class="hint">${o.created_at.slice(0, 16).replace('T', ' ')}</span>
        </div>
        <div class="hint" style="margin:8px 0">${mine.map(i => esc(i.name) + ' × ' + i.qty + ' — ваша выручка ' + fmt(i.seller_net || 0)).join('<br>')}</div>
        <div class="hint">👤 ${esc(o.customer.name)} · ${esc(o.customer.phone)} · ${esc(o.customer.address || '—')} · ${esc(o.delivery.label)}</div>
      </div>`;
    }).join('') || '<div class="panel hint">Заказов пока нет — поделитесь ссылкой на витрину!</div>'}`;
}

/* ---------------- баланс и выплаты ---------------- */
async function renderPayouts() {
  ME = await api('/api/seller/me');
  const payouts = await api('/api/seller/payouts');
  $('#tab-payouts').innerHTML = `
    <h2>Баланс и выплаты</h2>
    <div class="cards">
      <div class="stat"><div class="v">${fmt(ME.stats.balance)}</div><div class="l">Доступно к выплате</div></div>
      <div class="stat"><div class="v">${fmt(ME.held_balance || 0)}</div><div class="l">🔒 В холде (разморозится автоматически)</div></div>
      <div class="stat"><div class="v">${fmt(ME.stats.total_earned)}</div><div class="l">Заработано всего</div></div>
      <div class="stat"><div class="v">${ME.commission_percent || (ME.marketplace || {}).commission_percent || 15}%</div><div class="l">Комиссия площадки</div></div>
    </div>
    <div class="panel">
      <h3>Запросить выплату</h3>
      <p class="hint">Выплаты производит администратор площадки на согласованные реквизиты.</p>
      <div style="display:flex; gap:10px; align-items:center">
        <input class="field" id="po-amount" type="number" placeholder="Сумма, ₽" style="max-width:220px; margin:0">
        <button class="btn" onclick="requestPayout()">Запросить</button>
      </div>
    </div>
    <div class="panel" style="padding:0">
      <table class="table">
        <tr><th>Дата</th><th>Сумма</th><th>Статус</th></tr>
        ${payouts.map(x => `<tr><td class="hint">${x.created_at.slice(0, 10)}</td><td><b>${fmt(x.amount)}</b></td>
          <td>${x.status === 'paid' ? '✅ выплачено' : '⏳ запрошена'}</td></tr>`).join('') || '<tr><td colspan="3" class="hint">Выплат пока не было</td></tr>'}
      </table>
    </div>`;
}
async function requestPayout() {
  const amount = +$('#po-amount').value;
  if (!amount || amount <= 0) return toast('Укажите сумму', true);
  try {
    await api('/api/seller/payouts/request', { method: 'POST', body: JSON.stringify({ amount }) });
    toast('Заявка на выплату отправлена 💰');
    renderPayouts();
  } catch (e) { toast(e.message, true); }
}
window.requestPayout = requestPayout;

/* ---------------- настройки витрины ---------------- */
async function renderSettings() {
  ME = await api('/api/seller/me');
  $('#tab-settings').innerHTML = `
    <h2>Настройки витрины</h2>
    <div class="panel">
      <div class="form-grid">
        <div><label class="fld">Название магазина</label><input class="field" id="st-name" value="${esc(ME.store_name)}"></div>
        <div><label class="fld">Адрес витрины (slug)</label><input class="field" id="st-slug" value="${esc(ME.slug)}"></div>
        <div><label class="fld">Телефон</label><input class="field" id="st-phone" value="${esc(ME.phone)}"></div>
        <div><label class="fld">Email</label><input class="field" id="st-email" value="${esc(ME.email)}"></div>
        <div class="full"><label class="fld">Описание витрины</label><textarea class="field" id="st-desc">${esc(ME.description)}</textarea></div>
      </div>
      <button class="btn" onclick="saveSettings()">💾 Сохранить</button>
    </div>`;
}
async function saveSettings() {
  try {
    ME = await api('/api/seller/me', { method: 'PUT', body: JSON.stringify({
      store_name: $('#st-name').value, slug: $('#st-slug').value,
      phone: $('#st-phone').value, email: $('#st-email').value, description: $('#st-desc').value,
    }) });
    $('#sb-name').textContent = ME.store_name;
    $('#store-link').href = '/seller/' + ME.slug;
    toast('Сохранено ✅');
  } catch (e) { toast(e.message, true); }
}
window.saveSettings = saveSettings;

const RENDERERS = { dashboard: renderDashboard, products: renderProducts, promos: renderPromos,
                    orders: renderOrders, chat: renderChat, payouts: renderPayouts, settings: renderSettings };

async function init() {
  if (!KEY || !ME) { showLogin(); return; }
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  $('#sb-name').textContent = ME.store_name;
  $('#store-link').href = '/seller/' + ME.slug;
  for (const [tab, fn] of Object.entries(RENDERERS)) {
    try { await fn(); } catch (e) { $('#' + 'tab-' + tab).innerHTML = '<div class="panel err">' + esc(e.message) + '</div>'; }
  }
}
if (KEY) { doLogin(KEY).catch(() => {}); } else { showLogin(); }
