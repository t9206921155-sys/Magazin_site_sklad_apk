'use strict';
/* Telegram Shop — логика Mini App.
   Работает и внутри Telegram (берёт тему/initData из WebApp API), и в обычном браузере (превью). */

const tg = window.Telegram && window.Telegram.WebApp;
const inTG = !!tg;
if (tg) {
  try {
    tg.ready();
    tg.expand();
    if (tg.setHeaderColor) tg.setHeaderColor('secondary_bg_color');
  } catch (e) { /* не критично */ }
}

const $ = (sel, el) => (el || document).querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));
const fmt = n => new Intl.NumberFormat('ru-RU').format(n) + ' ₽';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const badgeHtml = p => {
  const b = [];
  if ((p.badges || []).includes('hit')) b.push('<span class="b-chip hot">🔥 Хит</span>');
  if ((p.badges || []).includes('new')) b.push('<span class="b-chip new">✨ Новинка</span>');
  if (p.old_price > p.price) b.push(`<span class="b-chip disc">−${Math.round((1 - p.price / p.old_price) * 100)}%</span>`);
  return b.join('');
};
const priceHtml = p => p.old_price > p.price
  ? `<span class="old-price">${fmt(p.old_price)}</span>${fmt(p.price)}`
  : fmt(p.price);
const logEvent = (type, payload) => {
  api('/api/events', { method: 'POST', body: JSON.stringify({ type, payload }) }).catch(() => {});
};
const haptic = type => { try { tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred(type || 'light'); } catch (e) {} };

function uid() {
  try { return crypto.randomUUID(); }
  catch (e) { return 'g-' + Date.now() + '-' + Math.random().toString(36).slice(2); }
}

const STATUS = {
  pending_payment: '⏳ ожидает оплаты',
  paid: '✅ оплачен',
  processing: '🔧 в обработке',
  shipped: '🚚 отправлен',
  delivered: '🎉 доставлен',
  cancelled: '❌ отменён',
};

const state = {
  config: {},
  catalog: [],
  categories: [],
  delivery: {},
  cart: {},
  category: 'all',
  catalogQ: '', catalogMin: 0, catalogMax: 0, catalogSort: '', catalogCondition: '', catalogPhoto: false, catalogNegotiable: false, catalogSeller: '',
  deliveryMethod: 'courier',
  screen: 'catalog',
  order: null,
  customer: {},
  promo: null, // {code, discount}
  bonus: { balance: 0, spend: 0 },
  fav: {},  // id -> {id,name,price,photo} (избранное, общий ключ с сайтом)
};

/* ---------------- избранное ---------------- */
const FAV_KEY = 'tgshop_fav';
function favLoad() {
  try {
    const list = JSON.parse(localStorage.getItem(FAV_KEY) || '[]');
    state.fav = {};
    list.forEach(f => { state.fav[f.id] = f; });
  } catch (e) { state.fav = {}; }
}
function favSave() {
  localStorage.setItem(FAV_KEY, JSON.stringify(Object.values(state.fav)));
}
function isFav(id) { return !!state.fav[id]; }
function toggleFav(p) {
  if (isFav(p.id)) delete state.fav[p.id];
  else state.fav[p.id] = { id: String(p.id), name: p.name, price: +p.price, photo: p.photo };
  favSave();
  renderFavButton(p.id);
  updateFavCount();
  haptic('light');
}
function renderFavButton(id) {
  const btn = $('#pm-fav');
  if (btn && $('#pm').dataset.id == id) {
    btn.textContent = isFav(id) ? '❤ В избранном' : '❤ В избранное';
    btn.style.background = isFav(id) ? '#f43f5e' : 'transparent';
    btn.style.color = isFav(id) ? '#fff' : '#f43f5e';
  }
}
function updateFavCount() {
  const n = Object.keys(state.fav).length;
  const el = $('#fav-count');
  if (el) el.textContent = n ? `(${n})` : '';
}
async function renderFavorites() {
  const ids = Object.keys(state.fav).join(',');
  if (!ids) {
    $('#fav-list').innerHTML = '<div class="empty">Пока пусто ❤<br>Нажимайте ❤ на товарах</div>';
    return;
  }
  try {
    const d = await api('/api/favorites?ids=' + ids);
    const ps = d.products || [];
    $('#fav-list').innerHTML = ps.length ? ps.map(p => `
      <div class="card row-card" style="display:flex; gap:12px; align-items:center; margin:10px 14px; padding:10px">
        <img src="${esc(p.photo)}" style="width:64px;height:64px;border-radius:12px;object-fit:cover" alt="">
        <div style="flex:1; min-width:0">
          <div class="card-name">${esc(p.name)}</div>
          <div class="card-price">${fmt(p.price)}</div>
          <div style="display:flex; gap:8px; margin-top:6px">
            <button class="btn small" data-action="open" data-id="${p.id}">Открыть</button>
            <button class="btn small ghost" data-action="add" data-id="${p.id}">🛒</button>
            <button class="btn small ghost" data-action="fav-remove" data-id="${p.id}">✕</button>
          </div>
        </div>
      </div>`).join('')
      : '<div class="empty">Сохранённые товары больше не в продаже</div>';
  } catch (e) { $('#fav-list').innerHTML = '<div class="empty">Не удалось загрузить избранное</div>'; }
}
favLoad();

const guestId = (() => {
  let g = localStorage.getItem('tgshop_guest');
  if (!g) { g = uid(); localStorage.setItem('tgshop_guest', g); }
  return g;
})();

try { state.cart = JSON.parse(localStorage.getItem('tgshop_cart') || '{}'); } catch (e) { state.cart = {}; }
try { state.customer = JSON.parse(localStorage.getItem('tgshop_customer') || '{}'); } catch (e) {}

function saveCart() { localStorage.setItem('tgshop_cart', JSON.stringify(state.cart)); }

/* ---------------- API ---------------- */
async function api(path, opts = {}) {
  const sep = path.includes('?') ? '&' : '?';
  const url = path + sep + 'guest_id=' + encodeURIComponent(guestId);
  const res = await fetch(url, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-Init-Data': tg ? (tg.initData || '') : '',
      ...(opts.headers || {}),
    },
  });
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error((data && (data.detail || data.message)) || ('Ошибка ' + res.status));
  return data;
}

/* ---------------- корзина ---------------- */
const cartLines = () => Object.entries(state.cart)
  .map(([id, qty]) => ({ product: state.catalog.find(p => p.id == id), qty }))
  .filter(l => l.product);
const cartCount = () => cartLines().reduce((s, l) => s + l.qty, 0);
const cartSubtotal = () => cartLines().reduce((s, l) => s + l.product.price * l.qty, 0);
const deliveryPrice = () => (state.delivery[state.deliveryMethod] || {}).price || 0;

function addToCart(id, qty = 1) {
  const p = state.catalog.find(x => x.id == id);
  if (!p) return;
  state.cart[id] = (state.cart[id] || 0) + qty;
  saveCart(); renderCartBar(); haptic('light');
  toast(`«${p.name}» в корзине 🛒`);
  logEvent('add_to_cart', { id });
}

function setQty(id, qty) {
  if (qty <= 0) delete state.cart[id];
  else state.cart[id] = Math.min(99, qty);
  saveCart(); renderCartBar();
}

/* ---------------- экраны ---------------- */
function go(screen) {
  state.screen = screen;
  document.querySelectorAll('.screen').forEach(s => s.classList.toggle('hidden', s.id !== 'screen-' + screen));
  renderCartBar();
  window.scrollTo(0, 0);
}

function renderCartBar() {
  const n = cartCount();
  $('#cart-bar').classList.toggle('hidden', !(state.screen === 'catalog' && n > 0));
  $('#bar-count').textContent = n;
  $('#bar-total').textContent = fmt(cartSubtotal());
  const badge = $('#cart-badge');
  badge.textContent = n;
  badge.classList.toggle('hidden', !n);
}

/* ---------------- каталог ---------------- */
function renderCatalog() {
  const cats = ['all', ...state.categories.filter(c => state.catalog.some(p => p.category === c))];
  $('#chips').innerHTML = cats.map(c =>
    `<button class="chip ${state.category === c ? 'active' : ''}" data-action="chip" data-cat="${esc(c)}">${c === 'all' ? 'Все' : esc(c)}</button>`
  ).join('');

  const q = state.catalogQ.toLowerCase(); let list = state.catalog.filter(p => (state.category === 'all' || p.category === state.category) && (!q || (p.name+' '+(p.description||'')).toLowerCase().includes(q)) && (!state.catalogMin || p.price >= state.catalogMin) && (!state.catalogMax || p.price <= state.catalogMax) && (!state.catalogCondition || p.condition === state.catalogCondition) && (!state.catalogPhoto || p.photo || (p.photos && p.photos.length)) && (!state.catalogNegotiable || p.negotiable) && (!state.catalogSeller || String(p.seller_slug||'').toLowerCase().includes(state.catalogSeller.toLowerCase()))); if(state.catalogSort==='price_asc') list.sort((a,b)=>a.price-b.price); if(state.catalogSort==='price_desc') list.sort((a,b)=>b.price-a.price); if(state.catalogSort==='new') list.sort((a,b)=>String(b.created_at||'').localeCompare(String(a.created_at||'')));
  $('#grid').innerHTML = list.map(p => `
    <div class="card" data-action="open" data-id="${p.id}">
      <div class="card-img">
        <img src="${esc(p.photo)}" alt="${esc(p.name)}" loading="lazy">
        <button class="card-fav ${isFav(p.id) ? 'on' : ''}" data-action="fav" data-id="${p.id}" aria-label="В избранное">${isFav(p.id) ? '❤' : '🤍'}</button>
      </div>
      <div class="card-body">
        <div>${badgeHtml(p)}${p.condition === 'used' ? '<span class="b-chip used">↻ Б/у</span>' : ''}${p.condition === 'defect' ? '<span class="b-chip defect">⚠ Дефекты</span>' : ''}</div>
        <div class="card-name">${esc(p.name)}</div>
        ${p.stock >= 0 && p.stock <= 5 ? `<div class="low-stock">Осталось ${p.stock} шт.</div>` : ''}
        <div class="card-foot">
          <div class="card-price">${priceHtml(p)}</div>
          <button class="plus" data-action="add" data-id="${p.id}" aria-label="В корзину">＋</button>
        </div>
      </div>
    </div>`).join('') || '<div class="empty">Каталог пуст 🙈</div>';
  updateFavCount();
}

function openProduct(id) {
  const p = state.catalog.find(x => x.id == id);
  if (!p) return;
  $('#pm-img').src = p.photo;
  $('#pm-img').alt = p.name;
  $('#pm-name').textContent = p.name;
  $('#pm-badges').innerHTML = badgeHtml(p);
  $('#pm-desc').textContent = p.description || '';
  $('#pm-price').textContent = fmt(p.price);
  if (p.old_price > p.price) {
    $('#pm-old-price').textContent = fmt(p.old_price);
    $('#pm-old-price').classList.remove('hidden');
  } else {
    $('#pm-old-price').classList.add('hidden');
  }
  $('#pm-stock').textContent = p.stock >= 0 ? `В наличии: ${p.stock} шт.` : '';
  $('#pm-qty').textContent = 1;
  $('#pm').dataset.id = id;
  $('#pm-cond').innerHTML = p.condition === 'used' ? '<span class="b-chip used">↻ Б/у</span>'
    : p.condition === 'defect' ? '<span class="b-chip defect">⚠ С дефектами — читайте описание</span>' : '';
  const params = p.params || {};
  const pkeys = Object.keys(params).filter(k => String(params[k] || '').trim());
  $('#pm-params').innerHTML = pkeys.length
    ? '<div class="hint">' + pkeys.slice(0, 6).map(k => `${esc(k)}: <b>${esc(params[k])}</b>`).join(' · ') + '</div>'
    : '';
  $('#pm-chat').classList.toggle('hidden', !p.seller_id);
  $('#pm').classList.add('open');
  renderFavButton(id);
  logEvent('view_product', { id });
}

/* ---------------- корзина ---------------- */
function renderCart() {
  const lines = cartLines();
  const el = $('#cart-items');
  if (!lines.length) {
    el.innerHTML = '<div class="empty">Корзина пуста 🧺</div>';
    $('#cart-foot').classList.add('hidden');
    return;
  }
  $('#cart-foot').classList.remove('hidden');
  el.innerHTML = lines.map(({ product: p, qty }) => `
    <div class="cart-row">
      <img class="cart-img" src="${esc(p.photo)}" alt="">
      <div class="cart-info">
        <div class="cart-name">${esc(p.name)}</div>
        <div class="cart-price">${fmt(p.price * qty)}</div>
        <div class="stepper">
          <button data-action="dec" data-id="${p.id}">−</button>
          <span>${qty}</span>
          <button data-action="inc" data-id="${p.id}">＋</button>
        </div>
      </div>
      <button class="cart-del" data-action="del" data-id="${p.id}" aria-label="Удалить">✕</button>
    </div>`).join('');
  $('#cart-subtotal').textContent = fmt(cartSubtotal());
}

/* ---------------- оформление ---------------- */
function collectCustomer() {
  if (state.screen !== 'checkout') return;
  const g = id => $(id).value.trim();
  state.customer = {
    name: g('#co-name'), phone: g('#co-phone'), city: g('#co-city'),
    address: g('#co-address'), comment: g('#co-comment'),
  };
  localStorage.setItem('tgshop_customer', JSON.stringify(state.customer));
}

function renderCheckout() {
  const c = state.customer;
  $('#co-name').value = c.name || '';
  $('#co-phone').value = c.phone || '';
  $('#co-city').value = c.city || '';
  $('#co-address').value = c.address || '';
  $('#co-comment').value = c.comment || '';

  $('#delivery-list').innerHTML = Object.entries(state.delivery).map(([id, d]) => `
    <label class="drow ${state.deliveryMethod === id ? 'active' : ''}" data-action="dm" data-id="${id}">
      <input type="radio" name="delivery" value="${id}" ${state.deliveryMethod === id ? 'checked' : ''}>
      <span class="dlabel">${esc(d.label)}</span>
      <span class="dprice">${d.price ? fmt(d.price) : 'бесплатно'}</span>
    </label>`).join('');

  const lines = cartLines();
  $('#co-items').innerHTML = lines.map(({ product: p, qty }) =>
    `<div class="sum-row"><span>${esc(p.name)} × ${qty}</span><span>${fmt(p.price * qty)}</span></div>`
  ).join('');

  updateCheckoutTotals();

  // выбор точки выдачи (5POST / Яндекс Доставка)
  const d = state.delivery[state.deliveryMethod];
  const hasPoints = d && (d.provider === 'fivepost' || d.provider === 'yandex');
  $('#co-point').classList.toggle('hidden', !hasPoints);
  $('#co-addr-hint').textContent = hasPoints ? 'Выберите точку выдачи из списка ниже' : 'Адрес нужен для курьера и почты';
  $('#co-addr-hint').classList.toggle('hidden', state.deliveryMethod === 'pickup' && !hasPoints);
  if (hasPoints) loadPoints(d.provider);

  // кнопка менеджера
  const mgr = (state.config.manager || {}).username;
  $('#co-manager-btn').classList.toggle('hidden', !mgr);

  // бонусные баллы
  loadBonus();
}

async function loadBonus() {
  try {
    const r = await api('/api/bonus');
    state.bonus.balance = r.balance || 0;
  } catch (e) {
    state.bonus.balance = 0;
  }
  const block = $('#co-bonus-block');
  block.classList.toggle('hidden', !state.bonus.balance);
  if (state.bonus.balance) {
    const maxSpend = Math.min(state.bonus.balance, cartSubtotal() - (state.promo ? state.promo.discount : 0));
    state.bonus.spend = Math.min(state.bonus.spend || 0, maxSpend);
    $('#co-bonus-amount').textContent = fmt(state.bonus.balance);
    $('#co-bonus-check').checked = state.bonus.spend > 0;
  }
  updateCheckoutTotals();
}

function updateCheckoutTotals() {
  const subtotal = cartSubtotal();
  const d = state.delivery[state.deliveryMethod];
  const discount = state.promo ? state.promo.discount : 0;
  const threshold = +state.config.free_delivery_from || 0;
  const bonusSpend = state.bonus.spend || 0;

  let dprice = d ? d.price : 0;
  if (threshold > 0 && state.deliveryMethod !== 'pickup' && subtotal >= threshold) dprice = 0;

  $('#co-delivery').textContent = dprice ? fmt(dprice) : 'бесплатно';
  $('#co-total').textContent = fmt(Math.max(0, subtotal - discount - bonusSpend + dprice));

  const discountRow = document.querySelector('.sum-row.discount');
  discountRow.classList.toggle('hidden', !discount);
  if (discount) $('#co-discount').textContent = '−' + fmt(discount);

  $('#co-bonus-row').classList.toggle('hidden', !bonusSpend);
  if (bonusSpend) $('#co-bonus-disc').textContent = '−' + fmt(bonusSpend);

  const freeHint = $('#co-free-hint');
  if (threshold > 0 && state.deliveryMethod !== 'pickup') {
    freeHint.classList.remove('hidden');
    freeHint.textContent = subtotal >= threshold
      ? `🎉 Доставка бесплатно (от ${fmt(threshold)})`
      : `До бесплатной доставки осталось ${fmt(threshold - subtotal)}`;
  } else {
    freeHint.classList.add('hidden');
  }

  const promoInfo = $('#co-promo-info');
  promoInfo.classList.toggle('hidden', !state.promo);
  if (state.promo) {
    promoInfo.textContent = `✅ Промокод ${state.promo.code} применён (−${fmt(discount)})`;
    promoInfo.style.color = 'var(--ok)';
  }
}

async function loadPoints(provider) {
  const sel = $('#co-point');
  const city = ($('#co-city').value || '').trim();
  if (!city) { sel.innerHTML = '<option value="">— сначала укажите город —</option>'; return; }
  sel.innerHTML = '<option value="">Загружаем точки выдачи…</option>';
  try {
    const res = await api('/api/delivery/points?method=' + provider + '&city=' + encodeURIComponent(city));
    if (res.points && res.points.length) {
      sel.innerHTML = '<option value="">— выберите точку выдачи —</option>' + res.points.map(p =>
        `<option value="${esc(p.id || p.mdm_code)}">${esc(p.name)} · ${esc(p.address || p.city || '')}</option>`).join('');
    } else {
      sel.innerHTML = `<option value="">${esc(res.error || 'Не удалось загрузить — укажите адрес вручную')}</option>`;
    }
  } catch (e) {
    sel.innerHTML = '<option value="">Не удалось загрузить — укажите адрес вручную</option>';
  }
}

async function applyPromo() {
  const code = $('#co-promo').value.trim();
  if (!code) return;
  try {
    const res = await api('/api/promo/validate', {
      method: 'POST',
      body: JSON.stringify({ code, subtotal: cartSubtotal() }),
    });
    if (!res.valid) {
      state.promo = null;
      $('#co-promo-info').textContent = '❌ ' + res.error;
      $('#co-promo-info').style.color = 'var(--danger)';
      $('#co-promo-info').classList.remove('hidden');
      updateCheckoutTotals();
      return;
    }
    state.promo = { code: code.toUpperCase(), discount: res.discount };
    toast('Промокод применён 🎟');
  } catch (e) {
    toast(e.message, true);
  }
  updateCheckoutTotals();
}

async function submitOrder() {
  collectCustomer();
  const c = state.customer;
  if (c.name.length < 2) return toast('Укажите имя', true);
  if (!/^[+\d][\d\s()\-]{5,}$/.test(c.phone)) return toast('Укажите корректный телефон', true);
  if (state.deliveryMethod !== 'pickup' && c.address.length < 5 && !c.point_id) {
    return toast('Укажите адрес доставки или выберите точку выдачи', true);
  }

  const btn = $('#co-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Создаём заказ…';
  try {
    const order = await api('/api/order', {
      method: 'POST',
      body: JSON.stringify({
        items: cartLines().map(l => ({ id: l.product.id, qty: l.qty })),
        customer: c,
        delivery_method: state.deliveryMethod,
        promo_code: state.promo ? state.promo.code : '',
        bonus_spend: state.bonus.spend || 0,
      }),
    });
    state.order = order;
    renderPayment();
    go('payment');
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Перейти к оплате';
  }
}

/* ---------------- оплата ---------------- */
let payMethods = [];
let selectedMethod = 'test';

async function renderPayment() {
  const o = state.order;
  $('#pay-id').textContent = o.id;
  $('#pay-total').textContent = fmt(o.total);
  try {
    payMethods = await api('/api/payment-methods');
  } catch (e) {
    payMethods = [{ id: 'test', label: '💳 Банковская карта (тест)', note: '' }];
  }
  if (!payMethods.find(m => m.id === selectedMethod)) selectedMethod = payMethods[0]?.id || 'test';
  const isTest = selectedMethod === 'test';
  const isTransfer = selectedMethod === 'transfer';
  const method = payMethods.find(m => m.id === selectedMethod);
  $('#pay-methods').innerHTML = payMethods.map(m => `
    <label class="drow ${selectedMethod === m.id ? 'active' : ''}" data-action="pay-method" data-id="${m.id}">
      <input type="radio" name="pm" ${selectedMethod === m.id ? 'checked' : ''}>
      <span class="dlabel">${esc(m.label)}</span>
    </label>`).join('');
  $('#card-panel').classList.toggle('hidden', !isTest);
  $('#transfer-panel').classList.toggle('hidden', !isTransfer);
  if (isTransfer && method && method.details) {
    const d = method.details;
    $('#transfer-details').innerHTML = [
      d.bank ? `<div class="sum-row"><span>Банк</span><span>${esc(d.bank)}</span></div>` : '',
      d.phone ? `<div class="sum-row"><span>Телефон (СБП)</span><span><b>${esc(d.phone)}</b></span></div>` : '',
      d.card ? `<div class="sum-row"><span>Карта</span><span><b>${esc(d.card)}</b></span></div>` : '',
      d.name ? `<div class="sum-row"><span>Получатель</span><span>${esc(d.name)}</span></div>` : '',
      `<div class="sum-row total"><span>Сумма перевода</span><span>${fmt(o.total)}</span></div>`,
    ].join('');
  }
  $('#pay-note').classList.add('hidden');
  const lbl = $('#btn-pay .pay-label');
  lbl.textContent = isTest ? `Оплатить ${fmt(o.total)}`
    : isTransfer ? '✅ Я оплатил(а) — жду подтверждения'
    : (selectedMethod === 'stars' ? 'Выставить счёт звёздами' : 'Перейти к оплате');
}

function openExternal(url) {
  if (tg && tg.openLink) {
    try { tg.openLink(url); return; } catch (e) {}
  }
  window.open(url, '_blank');
}

async function payNow() {
  const btn = $('#btn-pay');
  btn.disabled = true;
  btn.classList.add('loading');
  const lbl = $('#btn-pay .pay-label');
  try {
    if (selectedMethod === 'test') {
      lbl.textContent = 'Обработка платежа…';
      await sleep(1600); // имитация обращения к платёжному шлюзу
    }
    const res = await api(`/api/order/${state.order.id}/pay/${selectedMethod}`, { method: 'POST', body: '{}' });
    if (res.status === 'paid') {
      state.order = res;
      state.cart = {};
      saveCart(); renderCartBar(); haptic('medium');
      renderSuccess(); go('success');
      return;
    }
    if (res.confirmation_url || res.pay_url) {
      const note = $('#pay-note');
      note.textContent = 'Открыта страница оплаты. После оплаты заказ обновится автоматически…';
      note.classList.remove('hidden');
      openExternal(res.confirmation_url || res.pay_url);
      await pollPaid(btn);
      return;
    }
    if (res.message) {
      const note = $('#pay-note');
      note.textContent = res.message;
      note.classList.remove('hidden');
      await pollPaid(btn);
      return;
    }
    toast('Неизвестный ответ платёжной системы', true);
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
    renderPayment();
  }
}

async function pollPaid(btn) {
  for (let i = 0; i < 72; i++) {
    await sleep(2500);
    try {
      const o = await api('/api/order/' + state.order.id);
      if (o.status === 'paid') {
        state.order = o;
        state.cart = {};
        saveCart(); renderCartBar(); haptic('medium');
        renderSuccess(); go('success');
        return;
      }
    } catch (e) { /* повторяем */ }
  }
  if (btn) {
    btn.disabled = false;
    btn.classList.remove('loading');
  }
}

/* ---------------- успех ---------------- */
function renderSuccess() {
  $('#ok-id').textContent = state.order.id;
  $('#ok-total').textContent = fmt(state.order.total);
}

/* ---------------- мои заказы ---------------- */
async function openOrders() {
  try {
    const orders = await api('/api/orders');
    $('#orders-list').innerHTML = orders.length ? orders.map(o => `
      <div class="order-row">
        <div class="order-head"><b>${esc(o.id)}</b><span class="status ${esc(o.status)}">${STATUS[o.status] || esc(o.status)}</span></div>
        <div class="order-items">${o.items.map(i => esc(i.name) + ' × ' + i.qty).join(', ')}</div>
        ${o.delivery && o.delivery.tracking ? `<div class="hint" style="margin-top:6px">📦 Трек: <b>${esc(o.delivery.tracking)}</b></div>` : ''}
        <div class="order-foot"><span>${esc(o.created_at.slice(0, 10))} · ${esc(o.delivery.label)}</span><b>${fmt(o.total)}</b></div>
      </div>`).join('') : '<div class="empty">Заказов пока нет 😔</div>';
  } catch (e) {
    $('#orders-list').innerHTML = '<div class="empty">Не удалось загрузить заказы</div>';
  }
}

/* ---------------- тосты ---------------- */
function toast(msg, err) {
  const el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  $('#toasts').appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 300);
  }, 2400);
}

/* ---------------- чат с продавцами ---------------- */
const chatState = { thread: null };  // {product_id, seller_id, name}

async function renderChatThreads() {
  chatState.thread = null;
  $('#chat-title').textContent = 'Сообщения';
  $('#chat-input-row').style.display = 'none';
  try {
    const d = await api('/api/chat/threads');
    const th = d.threads || [];
    $('#chat-body').innerHTML = th.length ? th.map(t => `
      <div style="display:flex; gap:10px; align-items:center; padding:10px; border-bottom:1px solid var(--border, #eee); cursor:pointer"
           data-thread="${t.product_id}:${t.seller_id}:${esc(t.product_name)}">
        <img src="${esc(t.product_photo)}" style="width:44px;height:44px;border-radius:10px;object-fit:cover" alt="">
        <div style="flex:1; min-width:0">
          <b>${esc(t.product_name)}</b><br>
          <span class="hint">${esc(t.seller_name || 'Продавец')} · ${esc(t.last_text || '').slice(0, 50)}</span>
        </div>
        ${t.unread ? `<span style="background:var(--accent);color:#fff;border-radius:12px;padding:2px 8px;font-size:12px">${t.unread}</span>` : ''}
      </div>`).join('') : '<div class="empty">Сообщений пока нет.<br>Откройте товар и нажмите «Спросить продавца» 💬</div>';
    $('#chat-body').querySelectorAll('[data-thread]').forEach(el => el.addEventListener('click', () => {
      const [pid, sid, name] = el.dataset.thread.split(':');
      openChatThread(+pid, +sid, name);
    }));
  } catch (e) { $('#chat-body').innerHTML = '<div class="empty">Не удалось загрузить сообщения</div>'; }
}

async function openChatThread(productId, sellerId, name) {
  chatState.thread = { product_id: productId, seller_id: sellerId };
  $('#chat-title').textContent = name;
  $('#chat-input-row').style.display = 'flex';
  await renderChatMessages();
}

async function renderChatMessages() {
  const t = chatState.thread;
  if (!t) return;
  try {
    const ms = await api('/api/chat/messages?product_id=' + t.product_id + '&seller_id=' + t.seller_id);
    $('#chat-body').innerHTML = ms.map(m => `
      <div style="display:flex; ${m.sender === 'seller' ? 'justify-content:flex-end' : ''}; margin-bottom:8px">
        <div style="max-width:75%; padding:8px 12px; border-radius:12px; font-size:14px;
          background:${m.sender === 'seller' ? 'var(--accent)' : '#f0f0f0'};
          color:${m.sender === 'seller' ? '#fff' : 'inherit'}">
          ${esc(m.text)}<div style="font-size:10px; opacity:.7; margin-top:3px">${m.ts.slice(11, 16)}</div>
        </div>
      </div>`).join('') || '<div class="hint">Напишите первым — продавец ответит здесь.</div>';
    $('#chat-body').scrollTop = 99999;
  } catch (e) { $('#chat-body').innerHTML = '<div class="empty">Не удалось загрузить сообщения</div>'; }
}

async function sendChat() {
  const t = chatState.thread;
  const text = $('#chat-input').value.trim();
  if (!t || !text) return;
  try {
    await api('/api/chat/send', {
      method: 'POST',
      body: JSON.stringify({ ...t, text, buyer_name: (state.customer && state.customer.name) || 'Покупатель' }),
    });
    $('#chat-input').value = '';
    await renderChatMessages();
    haptic('light');
  } catch (e) { toast(e.message, true); }
}
window.sendChat = sendChat;

async function pollChatUnread() {
  try {
    const d = await api('/api/chat/unread');
    const badge = $('#chat-badge');
    if (d.unread > 0) { badge.textContent = d.unread; badge.classList.remove('hidden'); }
    else badge.classList.add('hidden');
  } catch (e) { /* гость без сессии — пропускаем */ }
}

/* ---------------- события ---------------- */
document.addEventListener('click', e => {
  const t = e.target.closest('[data-action]');
  if (!t) return;
  const a = t.dataset.action;
  const id = t.dataset.id;
  switch (a) {
    case 'chip': state.category = t.dataset.cat; renderCatalog(); break;
    case 'open': openProduct(id); break;
    case 'add': addToCart(id, 1); break;
    case 'inc': setQty(id, (state.cart[id] || 0) + 1); renderCart(); break;
    case 'dec': setQty(id, (state.cart[id] || 0) - 1); renderCart(); break;
    case 'del': delete state.cart[id]; saveCart(); renderCart(); renderCartBar(); break;
    case 'chat-open': renderChatThreads(); $('#chat').classList.add('open'); break;
    case 'chat-close': $('#chat').classList.remove('open'); break;
    case 'chat-back': renderChatThreads(); break;
    case 'pm-chat': {
      const p = state.catalog.find(x => x.id == $('#pm').dataset.id);
      if (p && p.seller_id) { openChatThread(p.id, p.seller_id, p.name + ' · ' + (p.seller_name || 'Продавец')); $('#chat').classList.add('open'); }
      break;
    }
    case 'fav': {
      const p = state.catalog.find(x => x.id == id);
      if (p) toggleFav(p);
      renderCatalog();
      break;
    }
    case 'pm-fav': {
      const p = state.catalog.find(x => x.id == $('#pm').dataset.id);
      if (p) toggleFav(p);
      break;
    }
    case 'favorites-open': renderFavorites(); go('favorites'); break;
    case 'fav-back': go('catalog'); break;
    case 'fav-remove': {
      const p = state.catalog.find(x => x.id == id);
      if (p) toggleFav(p); else { delete state.fav[id]; favSave(); updateFavCount(); }
      renderFavorites();
      break;
    }
    case 'cart-open': renderCart(); $('#cart').classList.add('open'); break;
    case 'cart-close': $('#cart').classList.remove('open'); break;
    case 'checkout':
      $('#cart').classList.remove('open');
      renderCheckout();
      go('checkout');
      break;
    case 'pm-add': {
      const q = Math.max(1, parseInt($('#pm-qty').textContent, 10) || 1);
      addToCart(+$('#pm').dataset.id, q);
      $('#pm').classList.remove('open');
      break;
    }
    case 'pm-buy': {
      const q = Math.max(1, parseInt($('#pm-qty').textContent, 10) || 1);
      addToCart(+$('#pm').dataset.id, q);
      $('#pm').classList.remove('open');
      renderCheckout();
      go('checkout');
      break;
    }
    case 'promo-apply': applyPromo(); break;
    case 'manager': {
      const u = (state.config.manager || {}).username;
      if (tg && tg.openTelegramLink) {
        try { tg.openTelegramLink('https://t.me/' + u); } catch (e) { window.open('https://t.me/' + u, '_blank'); }
      } else {
        window.open('https://t.me/' + u, '_blank');
      }
      break;
    }
    case 'pm-close': $('#pm').classList.remove('open'); break;
    case 'pm-inc': { const el = $('#pm-qty'); el.textContent = Math.min(99, +el.textContent + 1); break; }
    case 'pm-dec': { const el = $('#pm-qty'); el.textContent = Math.max(1, +el.textContent - 1); break; }
    case 'dm':
      collectCustomer();
      state.deliveryMethod = t.dataset.id;
      renderCheckout();
      break;
    case 'co-back': go('catalog'); break;
    case 'co-submit': submitOrder(); break;
    case 'pay-back': renderCheckout(); go('checkout'); break;
    case 'pay-method': selectedMethod = t.dataset.id; renderPayment(); break;
    case 'pay-now': payNow(); break;
    case 'ok-catalog': go('catalog'); break;
    case 'orders-open': openOrders(); go('orders'); break;
    case 'orders-back': go('catalog'); break;
  }
});

// закрытие листов по клику на затемнение
document.querySelectorAll('.sheet-overlay').forEach(ov => {
  ov.addEventListener('click', e => { if (e.target === ov) ov.classList.remove('open'); });
});

// перезагрузка списка точек выдачи при вводе города и выборе точки
document.addEventListener('input', e => { if (['catalog-q','catalog-seller','price-min','price-max'].includes(e.target.id)) { state.catalogQ=$('#catalog-q').value.trim(); state.catalogSeller=$('#catalog-seller').value.trim(); state.catalogMin=+$('#price-min').value||0; state.catalogMax=+$('#price-max').value||0; renderCatalog(); return; }
  if (e.target.id !== 'co-city') return;
  collectCustomer();
  const d = state.delivery[state.deliveryMethod];
  if (d && (d.provider === 'fivepost' || d.provider === 'yandex')) loadPoints(d.provider);
});
document.addEventListener('change', e => {
  if (e.target.id === 'catalog-condition') { state.catalogCondition=e.target.value; renderCatalog(); return; }
  if (e.target.id === 'catalog-photo') { state.catalogPhoto=e.target.checked; renderCatalog(); return; }
  if (e.target.id === 'catalog-negotiable') { state.catalogNegotiable=e.target.checked; renderCatalog(); return; }
  if (e.target.id === 'catalog-sort') { state.catalogSort=e.target.value; renderCatalog(); return; }
  if (e.target.id === 'co-point') {
    const opt = e.target.selectedOptions[0];
    state.customer.point_id = opt.value || '';
    $('#co-address').value = opt.value ? opt.textContent.trim() : '';
    collectCustomer();
  }
  if (e.target.id === 'co-bonus-check') {
    const maxSpend = Math.min(state.bonus.balance,
      cartSubtotal() - (state.promo ? state.promo.discount : 0));
    state.bonus.spend = e.target.checked ? Math.max(0, maxSpend) : 0;
    updateCheckoutTotals();
  }
});

/* ---------------- старт ---------------- */
async function init() {
  if (!inTG) $('#preview-badge').classList.remove('hidden');
  try {
    const cfg = await api('/api/config');
    state.config = cfg;
    state.delivery = cfg.delivery_methods || {};
    state.config.free_delivery_from = cfg.free_delivery_from || 0;
    state.config.manager = cfg.manager || {};
    $('#shop-name').textContent = cfg.shop_name || 'Telegram Shop';
    document.title = cfg.shop_name || 'Telegram Shop';
  } catch (e) { /* каталог всё равно попробуем загрузить */ }

  try {
    const cat = await api('/api/catalog');
    state.catalog = cat.products || [];
    state.categories = cat.categories || [];
  } catch (e) {
    toast('Не удалось загрузить каталог', true);
  }

  // чистим корзину от удалённых товаров
  Object.keys(state.cart).forEach(id => {
    if (!state.catalog.find(p => p.id == id)) delete state.cart[id];
  });
  saveCart();

  renderCatalog();
  renderCartBar();
  pollChatUnread();
  setInterval(pollChatUnread, 30000);
}

init();
