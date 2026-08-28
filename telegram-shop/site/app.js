'use strict';
/* Сайт-витрина Telegram Shop (SPA) */
const $ = (sel, el) => (el || document).querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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
function openManager() {
  const u = ((S.config.manager || {}).username || '').trim();
  if (u) window.open('https://t.me/' + u, '_blank');
}
window.openManager = openManager;

const STATUS = {
  pending_payment: '⏳ ожидает оплаты', paid: '✅ оплачен', processing: '🔧 в обработке',
  shipped: '🚚 отправлен', delivered: '🎉 доставлен', cancelled: '❌ отменён',
};

const S = { config: {}, catalog: [], categories: [], delivery: {}, cart: {}, customer: {}, deliveryMethod: 'courier', paymentMethod: 'test', promo: null, bonus: { balance: 0, spend: 0 } };

const guestId = (() => {
  let g = localStorage.getItem('tgshop_guest');
  if (!g) { g = (crypto.randomUUID ? crypto.randomUUID() : 'g-' + Date.now()); localStorage.setItem('tgshop_guest', g); }
  return g;
})();
try { S.cart = JSON.parse(localStorage.getItem('tgshop_cart') || '{}'); } catch (e) {}
try { S.customer = JSON.parse(localStorage.getItem('tgshop_customer') || '{}'); } catch (e) {}

const saveCart = () => localStorage.setItem('tgshop_cart', JSON.stringify(S.cart));

async function api(path, opts = {}) {
  const sep = path.includes('?') ? '&' : '?';
  const res = await fetch(path + sep + 'guest_id=' + encodeURIComponent(guestId), {
    ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error((data && (data.detail || data.message)) || ('Ошибка ' + res.status));
  return data;
}

/* ---------------- корзина ---------------- */
const lines = () => Object.entries(S.cart)
  .map(([id, qty]) => ({ p: S.catalog.find(x => x.id == id), qty })).filter(l => l.p);
const count = () => lines().reduce((s, l) => s + l.qty, 0);
const subtotal = () => lines().reduce((s, l) => s + l.p.price * l.qty, 0);

function saveSearch() {
  const q = ($('#search')?.value || '').trim();
  const cat = $('#cat')?.value || '';
  const sort = $('#sort')?.value || 'def';
  fetch('/api/saved_searches', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: q, filters: { category: cat, sort: sort } })
  }).then(async r => {
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Ошибка');
    toast('✅ Поиск сохранён');
  }).catch(e => { toast('❌ ' + e.message); });
}
function addCompare(id) {
  fetch('/api/compare', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'add', product_id: id })
  }).then(async r => {
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Ошибка');
    toast('✅ Добавлено в сравнение');
    logEvent('compare_add', { product_id: id });
  }).catch(e => { toast('❌ ' + e.message); });
}
function showSavedSearchNotify() {
  fetch('/api/saved_searches/notify', { headers: { 'Content-Type': 'application/json' } }).then(async r => {
    const data = await r.json();
    if (!data || !data.length) {
      toast('📭 Нет новых объявлений по сохранённым поискам');
      return;
    }
    const total = data.reduce((s, n) => s + (n.new_count || 0), 0);
    toast(`📬 Новые объявления по сохранённым поискам: ${total} шт.`);
  }).catch(e => { toast('❌ ' + e.message); });
}
function addToCart(id, qty = 1) {
  if (!S.catalog.find(x => x.id == id)) return;
  S.cart[id] = (S.cart[id] || 0) + qty;
  saveCart(); renderCount();
  toast('Товар добавлен в корзину 🛒');
  logEvent('add_to_cart', { id });
}
function showOfferForm(productId, currentPrice) {
  const msg = prompt('💬 Предложите свою цену для этого товара (оставьте поле пустым или нажмите Отмена, чтобы не отправлять):');
  if (msg === null) return; // отмена
  const priceStr = prompt('💰 Ваша предложенная цена (₽):', String(currentPrice > 0 ? Math.round(currentPrice * 0.8) : ''));
  if (priceStr === null) return;
  const proposed = parseInt(priceStr.replace(/\D/g, '') || '0');
  if (!proposed || proposed <= 0) { toast('❌ Укажите положительную цену'); return; }
  fetch('/api/offers', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, proposed_price: proposed, message: msg })
  }).then(async r => {
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Ошибка');
    toast('✅ Предложение цены отправлено! Продавец ответит.');
    logEvent('create_offer', { product_id: productId, proposed_price: proposed });
  }).catch(e => { toast('❌ ' + e.message); });
}
function setQty(id, qty) {
  if (qty <= 0) delete S.cart[id]; else S.cart[id] = Math.min(99, qty);
  saveCart(); renderCount();
}
function renderCount() { $('#cart-count').textContent = count(); }

/* ---------------- роутинг ---------------- */
function parseRoute() {
  const h = location.hash.slice(1) || '/';
  const parts = h.split('/').filter(Boolean);
  if (!parts.length) return { name: 'home' };
  if (parts[0] === 'p') return { name: 'product', id: +parts[1] };
  if (parts[0] === 'pay') return { name: 'pay', orderId: parts[1] };
  if (parts[0] === 'seller' && parts[2] === 'rating') return { name: 'seller_rating', slug: parts[1] };
  if (parts[0] === 'compare') return { name: 'compare' };
  if (parts[0] === 'success') return { name: 'success', orderId: parts[1] };
  return { name: parts[0] };
}

async function router() {
  const r = parseRoute();
  window.scrollTo(0, 0);
  const v = $('#view');
  try {
    if (r.name === 'home') v.innerHTML = renderHome();
    else if (r.name === 'catalog') { v.innerHTML = renderCatalogShell(); renderCatalogList(); }
    else if (r.name === 'product') v.innerHTML = renderProduct(r.id);
    else if (r.name === 'cart') { v.innerHTML = renderCart(); bindCheckout(); }
    else if (r.name === 'pay') await renderPay(r.orderId);
    else if (r.name === 'success') await renderSuccess(r.orderId);
    else if (r.name === 'seller_rating') v.innerHTML = await renderSellerRating(r.slug);
    else if (r.name === 'compare') v.innerHTML = renderCompare();
    else if (r.name === 'orders') { v.innerHTML = renderOrdersShell(); await loadOrders(); }
    else if (r.name === 'delivery') v.innerHTML = renderStatic('🚚 Доставка', S.config.texts?.delivery);
    else if (r.name === 'payments') v.innerHTML = renderStatic('💳 Оплата', S.config.texts?.payments);
    else if (r.name === 'about') v.innerHTML = renderStatic('🏬 О магазине', S.config.texts?.about);
    else v.innerHTML = '<div class="empty">Страница не найдена</div>';
  } catch (e) {
    v.innerHTML = '<div class="empty">Не удалось загрузить страницу</div>';
  }
}

/* ---------------- страницы ---------------- */
function cardHtml(p) {
  return `
  <div class="card" onclick="location.hash='#/p/${p.id}'">
    <div class="card-img"><img src="${esc(p.photo)}" alt="${esc(p.name)}" loading="lazy"></div>
    <div class="card-body">
      <div class="b-chips">${badgeHtml(p)}</div>
      <div class="card-cat">${esc(p.category || '')}</div>
      <div class="card-name">${esc(p.name)}</div>
      ${p.stock >= 0 && p.stock <= 5 ? `<div class="low-stock">Осталось ${p.stock} шт.</div>` : ''}
      <div class="card-foot">
        <div class="price">${priceHtml(p)}</div>
        <button class="add-btn" onclick="event.stopPropagation(); addToCart(${p.id})">＋</button>
        <button class="btn ghost" style="padding:6px 10px;font-size:12px;margin-left:4px"
                onclick="event.stopPropagation(); addCompare(${p.id})">⚖️</button>
      </div>
    </div>
  </div>`;
}

function renderHome() {
  const cats = S.categories.slice(0, 5);
  const featured = S.catalog.slice(0, 8);
  return `
  <div class="hero">
    <h1>${esc(S.config.shop_name)} — всё нужное в одном месте</h1>
    <p>Гаджеты, аксессуары, уют для дома и подарки. Доставка по всей стране, удобная оплата.</p>
    <button class="btn-light" onclick="location.hash='#/catalog'">Перейти в каталог</button>
  </div>
  <div class="sect">
    <div class="benefits">
      <div class="benefit"><div class="ico">🚚</div><b>Быстрая доставка</b><p>Курьер, почта и СДЭК — расчёт стоимости онлайн</p></div>
      <div class="benefit"><div class="ico">💳</div><b>Любая оплата</b><p>Карты, СБП, криптовалюта, Telegram Stars</p></div>
      <div class="benefit"><div class="ico">🔁</div><b>Синхронизация с 1С</b><p>Каталог и заказы обновляются автоматически</p></div>
      <div class="benefit"><div class="ico">📦</div><b>Отслеживание</b><p>Статус каждого заказа в личном разделе</p></div>
    </div>
  </div>
  ${cats.length ? `<div class="sect"><h2>Категории</h2>
    <div class="toolbar">${cats.map(c => `<button class="select" onclick="location.hash='#/catalog'">${esc(c)}</button>`).join('')}</div></div>` : ''}
  <div class="sect"><h2>Популярное</h2>
    ${S.catalog.length ? `<div class="grid">${featured.map(cardHtml).join('')}</div>` : '<div class="empty">Каталог пуст 🙈</div>'}
  </div>`;
}

function renderCatalogShell() {
  const catOpts = S.categories.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
  return `
  <div class="sect">
    <h2>Каталог</h2>
    <div class="toolbar">
      <input class="search" id="search" placeholder="🔍 Поиск по названию…" oninput="renderCatalogList()">
      <select class="select" id="cat" onchange="renderCatalogList()"><option value="">Все категории</option>${catOpts}</select>
      <select class="select" id="sort" onchange="renderCatalogList()">
        <option value="def">По умолчанию</option>
        <option value="price_asc">Сначала дешевле</option>
        <option value="price_desc">Сначала дороже</option>
      </select>
      <button class="btn ghost" onclick="saveSearch()">💾 Сохранить поиск</button>
      <button class="btn ghost" onclick="showSavedSearchNotify()">📬 Уведомления</button>
    </div>
    <div class="grid" id="grid"></div>
  </div>`;
}

function renderCatalogList() {
  const q = ($('#search')?.value || '').toLowerCase();
  const cat = $('#cat')?.value || '';
  const sort = $('#sort')?.value || 'def';
  let list = S.catalog.filter(p =>
    (!q || p.name.toLowerCase().includes(q)) && (!cat || p.category === cat));
  if (sort === 'price_asc') list = [...list].sort((a, b) => a.price - b.price);
  if (sort === 'price_desc') list = [...list].sort((a, b) => b.price - a.price);
  $('#grid').innerHTML = list.length ? list.map(cardHtml).join('') : '<div class="empty">Ничего не найдено 🔍</div>';
}

function renderProduct(id) {
  const p = S.catalog.find(x => x.id === id);
  if (!p) return '<div class="empty">Товар не найден</div>';
  logEvent('view_product', { id });
  return `
  <div class="product">
    <div class="product-img"><img src="${esc(p.photo)}" alt="${esc(p.name)}"></div>
    <div>
      <div class="p-head"><a class="back-link" href="#/catalog">← Назад в каталог</a>
        <span>${badgeHtml(p)}</span></div>
      <h1>${esc(p.name)}</h1>
      <div class="p-cat">${esc(p.category || '')} • Артикул: ${esc(p.code || '—')}</div>
      <div class="p-desc">${esc(p.description || '')}</div>
      <div class="p-price">${priceHtml(p)}</div>
      ${p.stock >= 0 ? `<div class="low-stock" style="margin-bottom:12px">В наличии: ${p.stock} шт.</div>` : ''}
      <div>
        <div class="qty">
          <button onclick="pqty(-1)">−</button><span id="pq">1</span><button onclick="pqty(1)">＋</button>
        </div>
        <button class="buy-btn" id="buybtn" onclick="addToCart(${p.id}, +document.getElementById('pq').textContent); location.hash='#/cart'">В корзину</button>
        <button class="btn ghost" style="display:inline-block;width:auto;margin-left:10px;padding:14px 22px"
                onclick="showOfferForm(${p.id}, ${p.price})">💬 Предложить цену</button>
        <button class="btn ghost" style="display:inline-block;width:auto;margin-left:10px;padding:14px 22px"
                onclick="addToCart(${p.id}, +document.getElementById('pq').textContent); location.hash='#/cart'">⚡ Купить сейчас</button>
      </div>
      <div class="hint" style="margin-top:16px">Доставка рассчитывается при оформлении. Оплата: карта, СБП, криптовалюта.</div>
    </div>
  </div>`;
}
function renderCompare() {
  fetch('/api/compare', { headers: { 'Content-Type': 'application/json' } }).then(async r => {
    const data = await r.json();
    const items = data || [];
    const v = $('#view');
    if (!items.length) {
      v.innerHTML = '<div class="empty">Сравнение пусто. Добавьте товары через кнопку ⚖️ в карточках.</div>';
      return;
    }
    const headers = ['Параметр', ...items.map(p => p.name || '—')];
    const rows = [
      ['Фото', ...items.map(p => `<img src="${esc(p.photo)}" alt="${esc(p.name)}" style="max-width:120px;max-height:100px;">`)],
      ['Категория', ...items.map(p => esc(p.category || ''))],
      ['Цена', ...items.map(p => fmt(p.price))],
      ['Старая цена', ...items.map(p => p.old_price > 0 ? fmt(p.old_price) : '—')],
      ['Наличие', ...items.map(p => p.stock >= 0 ? `${p.stock} шт.` : '—')],
      ['Артикул', ...items.map(p => esc(p.code || '—'))],
      ['Описание', ...items.map(p => `<div style="font-size:13px;color:#555">${esc(p.description || '').slice(0, 120)}${(p.description || '').length > 120 ? '…' : ''}</div>`)],
    ];
    v.innerHTML = `
    <div class="sect">
      <h2>⚖️ Сравнение товаров (${items.length})</h2>
      <div style="overflow:auto">
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <thead><tr style="background:#f6f7fb">${headers.map(h => `<th style="padding:10px;text-align:left;border-bottom:2px solid #d1d5db">${esc(typeof h === 'string' ? h : '')}</th>`).join('')}</tr></thead>
          <tbody>${rows.map(row => `<tr style="border-bottom:1px solid #eaeaea">${row.map(cell => `<td style="padding:10px;vertical-align:top">${cell}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>
      </div>
      <div style="margin-top:12px">${items.map(p => `<button class="btn ghost" onclick="location.hash='#/p/${p.id}'">${esc(p.name)}</button>`).join(' ')}</div>
    </div>`;
  }).catch(e => {
    $('#view').innerHTML = '<div class="empty">Не удалось загрузить сравнение</div>';
  });
}

async function renderSellerRating(slug) {
  const v = $('#view');
  v.innerHTML = '<div class="empty">Загружаем рейтинг продавца…</div>';
  try {
    const data = await api('/api/seller/' + encodeURIComponent(slug) + '/rating');
    const s = data.seller || {};
    const rating = data.rating_summary || {};
    const reviews = data.reviews || [];
    const stats = data.review_stats || { avg: 0, count: 0 };
    const details = data.rating_details || {};
    v.innerHTML = `
    <div class="sect">
      <a class="back-link" href="#/catalog">← Назад в каталог</a>
      <h2>⭐ Рейтинг продавца: ${esc(s.store_name || s.slug || slug)}</h2>
      <div style="margin-top:14px">
        <div style="font-size:48px;font-weight:bold;color:#4f46e5">${rating.rating ? rating.rating.toFixed(1) : '—'}/5.0</div>
        <div class="hint">Средняя оценка: ${stats.avg ? stats.avg.toFixed(1) : '—'} из 5 (${stats.count || 0} отзывов о продавце)</div>
        <div class="hint">Одобрено отзывов: ${rating.reviews_approved || 0} / Всего: ${rating.reviews_total || 0} (${rating.approval_rate ? rating.approval_rate.toFixed(1) + '%' : '—'})</div>
        <div class="hint">Ответов в чатах: ${rating.response_rate || 0}% • Скорость ответа: ${rating.response_time_hours || 24} ч</div>
        <div class="hint">Статус: ${rating.status || '—'} • Тариф: ${(rating.plan || '—')}</div>
      </div>
      <h3 style="margin-top:22px">Отзывы о продавце</h3>
      ${reviews.length ? reviews.map(r => `
        <div style="border:1px solid #eaeaea;padding:14px;margin:8px 0;border-radius:8px;background:#fafbfc">
          <div><b>${esc(r.author || 'Гость')}</b> · <span style="color:#f59e0b">${'★'.repeat(r.rating || 5)}${'☆'.repeat(5 - (r.rating || 5))}</span> · ${esc(r.created_at ? r.created_at.slice(0, 10) : '')}</div>
          <div style="margin-top:6px;color:#333">${esc(r.text || '')}</div>
        </div>`).join('') : '<div class="empty">Отзывов о продавце пока нет.</div>'}
    </div>`;
  } catch (e) {
    v.innerHTML = '<div class="empty">Не удалось загрузить рейтинг продавца</div>';
  }
}
  fetch('/api/compare', { headers: { 'Content-Type': 'application/json' } }).then(async r => {
    const data = await r.json();
    const items = data || [];
    const v = $('#view');
    if (!items.length) {
      v.innerHTML = '<div class="empty">Сравнение пусто. Добавьте товары через кнопку ⚖️ в карточках.</div>';
      return;
    }
    const headers = ['Параметр', ...items.map(p => p.name || '—')];
    const rows = [
      ['Фото', ...items.map(p => `<img src="${esc(p.photo)}" alt="${esc(p.name)}" style="max-width:120px;max-height:100px;">`)],
      ['Категория', ...items.map(p => esc(p.category || ''))],
      ['Цена', ...items.map(p => fmt(p.price))],
      ['Старая цена', ...items.map(p => p.old_price > 0 ? fmt(p.old_price) : '—')],
      ['Наличие', ...items.map(p => p.stock >= 0 ? `${p.stock} шт.` : '—')],
      ['Артикул', ...items.map(p => esc(p.code || '—'))],
      ['Описание', ...items.map(p => `<div style="font-size:13px;color:#555">${esc(p.description || '').slice(0, 120)}${(p.description || '').length > 120 ? '…' : ''}</div>`)],
    ];
    v.innerHTML = `
    <div class="sect">
      <h2>⚖️ Сравнение товаров (${items.length})</h2>
      <div style="overflow:auto">
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <thead><tr style="background:#f6f7fb">${headers.map(h => `<th style="padding:10px;text-align:left;border-bottom:2px solid #d1d5db">${esc(typeof h === 'string' ? h : '')}</th>`).join('')}</tr></thead>
          <tbody>${rows.map(row => `<tr style="border-bottom:1px solid #eaeaea">${row.map(cell => `<td style="padding:10px;vertical-align:top">${cell}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>
      </div>
      <div style="margin-top:12px">${items.map(p => `<button class="btn ghost" onclick="location.hash='#/p/${p.id}'">${esc(p.name)}</button>`).join(' ')}</div>
    </div>`;
  }).catch(e => {
    $('#view').innerHTML = '<div class="empty">Не удалось загрузить сравнение</div>';
  });
}
window.pqty = d => { const el = $('#pq'); el.textContent = Math.min(99, Math.max(1, +el.textContent + d)); };

function renderCart() {
  const ls = lines();
  if (!ls.length) return '<div class="sect"><h2>Корзина</h2><div class="empty">Корзина пуста 🧺</div></div>';
  return `
  <div class="sect"><h2>Корзина</h2></div>
  <div class="cart-grid">
    <div>
      ${ls.map(({ p, qty }) => `
      <div class="cart-line">
        <img src="${esc(p.photo)}" alt="">
        <div class="cl-info">
          <div class="cl-name">${esc(p.name)}</div>
          <div class="cl-price">${fmt(p.price * qty)}</div>
          <div class="qty">
            <button onclick="cartQty(${p.id},-1); router()">−</button><span>${qty}</span><button onclick="cartQty(${p.id},1); router()">＋</button>
          </div>
        </div>
        <button class="cl-del" onclick="cartQty(${p.id},-999); router()">✕</button>
      </div>`).join('')}
    </div>
    <div class="panel">
      <h3>Оформление заказа</h3>
      <input class="field" id="f-name" placeholder="Имя *" value="${esc(S.customer.name || '')}">
      <input class="field" id="f-phone" placeholder="Телефон *" value="${esc(S.customer.phone || '')}">
      <input class="field" id="f-city" placeholder="Город" value="${esc(S.customer.city || '')}">
      <input class="field" id="f-address" placeholder="Адрес доставки *" value="${esc(S.customer.address || '')}">
      <select class="field hidden" id="f-point"><option value="">— выберите постамат 5POST —</option></select>
      <input class="field" id="f-comment" placeholder="Комментарий" value="${esc(S.customer.comment || '')}">
      <h3 style="margin-top:14px">Доставка</h3>
      <div id="dm-list"></div>
      <h3 style="margin-top:14px">Оплата</h3>
      <div id="pm-list"></div>
      <div class="promo-row">
        <input class="field" id="f-promo" placeholder="🎟 Промокод" autocomplete="off">
        <button class="btn ghost" id="promo-btn" type="button">ОК</button>
      </div>
      <div class="hint" id="promo-info" style="margin:6px 2px 0; min-height:16px"></div>
      <label class="drow" id="bonus-block" style="display:none">
        <input type="checkbox" id="f-bonus-check">
        <span class="lbl">💎 Списать бонусные баллы</span>
        <span class="prc" id="f-bonus-amount">—</span>
      </label>
      <div class="sum-row"><span>Товары</span><span id="s-sub">${fmt(subtotal())}</span></div>
      <div class="sum-row disc" id="disc-row" style="display:none"><span>Скидка</span><span id="s-disc">—</span></div>
      <div class="sum-row disc" id="bonus-row" style="display:none"><span>Бонусы</span><span id="s-bonus">—</span></div>
      <div class="sum-row"><span>Доставка</span><span id="s-del">—</span></div>
      <div class="sum-row total"><span>Итого</span><span id="s-total">—</span></div>
      <div class="free-note" id="free-note" style="display:none"></div>
      <button class="btn primary" id="submit-btn" style="margin-top:14px">Оформить заказ</button>
      <button class="btn ghost" id="mgr-btn" style="display:none;margin-top:8px" onclick="openManager()">💬 Связаться с менеджером</button>
    </div>
  </div>`;
}
window.cartQty = setQty;

function bindCheckout() {
  const dms = S.delivery;
  $('#dm-list').innerHTML = Object.entries(dms).map(([id, d]) => `
    <label class="drow ${S.deliveryMethod === id ? 'active' : ''}">
      <input type="radio" name="dm" value="${id}" ${S.deliveryMethod === id ? 'checked' : ''} onchange="setDm('${id}')">
      <span class="lbl">${esc(d.label)}</span>
      <span class="prc" id="pr-${id}">${d.price ? fmt(d.price) : 'бесплатно'}</span>
    </label>`).join('');

  const pms = [
    { id: 'test', label: '💳 Банковская карта (тест)' },
    { id: 'transfer', label: '💸 Перевод по СБП или карте', disabled: !(S.config.transfer_ok) },
    { id: 'yookassa', label: '💳 Карта / СБП (ЮKassa)', disabled: !(S.config.yookassa_ok) },
    { id: 'tbank', label: '🏦 Т-Банк — карты, СБП', disabled: !(S.config.tbank_ok) },
    { id: 'cryptobot', label: '💎 CryptoBot (криптовалюта)', disabled: !(S.config.cryptobot_ok) },
  ];
  $('#pm-list').innerHTML = pms.filter(m => !m.disabled).map((m, i) => `
    <label class="drow ${S.paymentMethod === m.id ? 'active' : ''}">
      <input type="radio" name="pm" value="${m.id}" ${S.paymentMethod === m.id ? 'checked' : ''} onchange="S.paymentMethod='${m.id}'">
      <span class="lbl">${m.label}</span>
    </label>`).join('');

  updateTotals();
  setupPoints();
  $('#f-city').onchange = e => { updateTotals(); };
  $('#promo-btn').addEventListener('click', applyPromoSite);
  $('#f-bonus-check').addEventListener('change', e => {
    const maxSpend = Math.min(S.bonus.balance, subtotal() - (S.promo ? S.promo.discount : 0));
    S.bonus.spend = e.target.checked ? Math.max(0, maxSpend) : 0;
    updateTotals();
  });
  $('#submit-btn').addEventListener('click', submitOrder);
  $('#mgr-btn').style.display = ((S.config.manager || {}).username || '').trim() ? '' : 'none';
  loadBonus();
}

async function loadBonus() {
  try {
    const r = await api('/api/bonus');
    S.bonus.balance = r.balance || 0;
  } catch (e) {
    S.bonus.balance = 0;
  }
  if (S.bonus.balance) {
    $('#bonus-block').style.display = '';
    $('#f-bonus-amount').textContent = fmt(S.bonus.balance);
  }
}

async function applyPromoSite() {
  const code = $('#f-promo').value.trim();
  if (!code) return;
  try {
    const res = await api('/api/promo/validate', {
      method: 'POST', body: JSON.stringify({ code, subtotal: subtotal() }),
    });
    if (!res.valid) {
      S.promo = null;
      $('#promo-info').textContent = '❌ ' + res.error;
      $('#promo-info').style.color = '#e5484d';
      updateTotals();
      return;
    }
    S.promo = { code: code.toUpperCase(), discount: res.discount };
    $('#promo-info').textContent = `✅ Промокод ${S.promo.code} применён (−${fmt(res.discount)})`;
    $('#promo-info').style.color = '#2ecc71';
    toast('Промокод применён 🎟');
  } catch (e) {
    toast(e.message, true);
  }
  updateTotals();
}

function setupPoints() {
  const d = S.delivery[S.deliveryMethod];
  const hasPoints = d && (d.provider === 'fivepost' || d.provider === 'yandex');
  const sel = $('#f-point');
  sel.classList.toggle('hidden', !hasPoints);
  if (!hasPoints) return;
  $('#f-city').onchange = e => { loadPoints(d.provider); };
  loadPoints(d.provider);
}

async function loadPoints(provider) {
  const sel = $('#f-point');
  const city = ($('#f-city')?.value || '').trim();
  if (!city) { sel.innerHTML = '<option value="">— сначала укажите город —</option>'; return; }
  sel.innerHTML = '<option value="">Загружаем точки выдачи…</option>';
  try {
    const res = await api('/api/delivery/points?method=' + provider + '&city=' + encodeURIComponent(city));
    if (res.points && res.points.length) {
      sel.innerHTML = '<option value="">— выберите точку выдачи —</option>' + res.points.map(p =>
        `<option value="${esc(p.id || p.mdm_code)}">${esc(p.name)} · ${esc(p.address || p.city || '')}</option>`).join('');
    } else {
      sel.innerHTML = `<option value="">${esc(res.error || 'Не удалось загрузить список — укажите адрес вручную')}</option>`;
    }
  } catch (e) {
    sel.innerHTML = '<option value="">Не удалось загрузить список — укажите адрес вручную</option>';
  }
  sel.addEventListener('change', () => {
    const opt = sel.selectedOptions[0];
    S.customer.point_id = opt.value;
    if (opt.value) $('#f-address').value = opt.textContent.trim();
  });
}
window.setDm = id => { S.deliveryMethod = id; bindCheckout(); };

function deliveryPriceNow() {
  const d = S.delivery[S.deliveryMethod];
  return d ? d.price : 0;
}
function updateTotals() {
  const d = S.delivery[S.deliveryMethod];
  const isCdek = d && d.provider === 'cdek';
  const isYandex = d && d.provider === 'yandex';
  const city = $('#f-city')?.value.trim() || '';
  const discount = S.promo ? S.promo.discount : 0;
  const bonusSpend = S.bonus.spend || 0;
  const threshold = +S.config.free_delivery_from || 0;

  $('#disc-row').style.display = discount ? '' : 'none';
  if (discount) $('#s-disc').textContent = '−' + fmt(discount);
  $('#bonus-row').style.display = bonusSpend ? '' : 'none';
  if (bonusSpend) $('#s-bonus').textContent = '−' + fmt(bonusSpend);
  $('#s-sub').textContent = fmt(subtotal());

  const update = async () => {
    let price = d ? d.price : 0;
    if (threshold > 0 && S.deliveryMethod !== 'pickup' && subtotal() >= threshold) price = 0;
    if (isCdek && city && price !== 0) {
      const r = await api('/api/delivery/calc', { method: 'POST', body: JSON.stringify({ method: S.deliveryMethod, city }) });
      price = r.price;
      $('#pr-' + S.deliveryMethod).textContent = fmt(price);
      $('#s-del').textContent = r.calculated ? fmt(price) + ' (СДЭК)' : fmt(price);
    } else if (isYandex && city) {
      const r = await api('/api/delivery/calc', { method: 'POST', body: JSON.stringify({
        method: S.deliveryMethod, city, point_id: S.customer.point_id || '' }) });
      price = r.price;
      $('#s-del').textContent = r.calculated ? fmt(price) + ' (Яндекс)' : fmt(price);
    } else if (isCdek && !city && price !== 0) {
      $('#s-del').textContent = 'укажите город';
    } else if (price === 0) {
      $('#s-del').textContent = 'бесплатно 🎉';
    } else {
      $('#s-del').textContent = d.price ? fmt(d.price) : 'бесплатно';
    }
    $('#s-total').textContent = fmt(Math.max(0, subtotal() - discount - bonusSpend + price));
    const note = $('#free-note');
    if (threshold > 0 && S.deliveryMethod !== 'pickup' && price !== 0 && subtotal() < threshold) {
      note.style.display = '';
      note.textContent = `До бесплатной доставки осталось ${fmt(threshold - subtotal())}`;
    } else if (price === 0 && threshold > 0 && S.deliveryMethod !== 'pickup') {
      note.style.display = '';
      note.textContent = `🎉 Бесплатная доставка от ${fmt(threshold)}`;
    } else {
      note.style.display = 'none';
    }
  };
  update();
}

async function submitOrder() {
  const c = {
    name: $('#f-name').value.trim(), phone: $('#f-phone').value.trim(),
    city: $('#f-city').value.trim(), address: $('#f-address').value.trim(),
    comment: $('#f-comment').value.trim(), point_id: S.customer.point_id || '',
  };
  if (c.name.length < 2) return toast('Укажите имя', true);
  if (c.phone.length < 6) return toast('Укажите корректный телефон', true);
  if (S.deliveryMethod !== 'pickup' && c.address.length < 5 && !c.point_id) {
    return toast('Укажите адрес доставки или выберите точку выдачи', true);
  }
  S.customer = c;
  localStorage.setItem('tgshop_customer', JSON.stringify(c));
  const btn = $('#submit-btn');
  btn.disabled = true; btn.textContent = 'Создаём заказ…';
  try {
    const order = await api('/api/order', {
      method: 'POST',
      body: JSON.stringify({
        items: lines().map(l => ({ id: l.p.id, qty: l.qty })),
        customer: c, delivery_method: S.deliveryMethod, payment_method: S.paymentMethod,
        promo_code: S.promo ? S.promo.code : '', bonus_spend: S.bonus.spend || 0,
      }),
    });
    location.hash = '#/pay/' + order.id;
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false; btn.textContent = 'Оформить заказ';
  }
}

/* ---------------- оплата ---------------- */
async function renderPay(orderId) {
  const v = $('#view');
  v.innerHTML = `<div class="pay-wrap"><div class="empty">Загружаем заказ…</div></div>`;
  let order;
  try { order = await api('/api/order/' + orderId); }
  catch (e) { v.innerHTML = '<div class="empty">Заказ не найден</div>'; return; }
  if (order.status === 'paid') { location.hash = '#/success/' + orderId; return; }

  const isTest = order.payment_method === 'test';
  const isTransfer = order.payment_method === 'transfer';
  let transferHtml = '';
  if (isTransfer) {
    try {
      const methods = await api('/api/payment-methods');
      const m = methods.find(x => x.id === 'transfer');
      if (m && m.details) {
        const d = m.details;
        transferHtml = `
        <div class="pay-row" style="text-align:left">
          <label>Реквизиты для перевода</label>
          ${d.bank ? `<div class="hint" style="margin:2px 0">Банк: ${esc(d.bank)}</div>` : ''}
          ${d.phone ? `<div class="hint" style="margin:2px 0">СБП (телефон): <b>${esc(d.phone)}</b></div>` : ''}
          ${d.card ? `<div class="hint" style="margin:2px 0">Карта: <b>${esc(d.card)}</b></div>` : ''}
          ${d.name ? `<div class="hint" style="margin:2px 0">Получатель: ${esc(d.name)}</div>` : ''}
          <div class="hint" style="margin-top:8px">Переведите сумму и нажмите кнопку — мы проверим поступление и подтвердим заказ.</div>
        </div>`;
      }
    } catch (e) {}
  }
  v.innerHTML = `
  <div class="pay-wrap">
    <div class="pay-card">
      <h2 style="margin:0">Оплата заказа ${esc(order.id)}</h2>
      <div class="pay-total">${fmt(order.total)}</div>
      <div class="hint">Способ: ${order.payment_method === 'yookassa' ? 'ЮKassa' : order.payment_method === 'cryptobot' ? 'CryptoBot' : order.payment_method === 'transfer' ? 'перевод по СБП/карте' : 'тестовая карта'}</div>
      ${isTest ? `
      <div class="pay-row">
        <label>Номер карты</label>
        <input class="field" id="card-num" value="4242 4242 4242 4242">
      </div>
      <div class="row2">
        <div class="pay-row" style="flex:1"><label>Срок</label><input class="field" id="card-exp" value="12/28"></div>
        <div class="pay-row" style="flex:1"><label>CVC</label><input class="field" id="card-cvc" value="123"></div>
      </div>
      <div class="hint mt">🧪 Тестовый режим: данные никуда не отправляются, деньги не списываются.</div>` : ''}
      ${transferHtml}
      <button class="btn ${isTest ? 'ok' : 'primary'} mt" id="pay-btn">${isTest ? `Оплатить ${fmt(order.total)}` : isTransfer ? '✅ Я оплатил(а) — жду подтверждения' : 'Перейти к оплате'}</button>
      <div class="hint mt" id="pay-note"></div>
    </div>
  </div>`;
  $('#pay-btn').addEventListener('click', () => doPay(order));
}

async function doPay(order) {
  const btn = $('#pay-btn');
  btn.disabled = true;
  try {
    if (order.payment_method === 'test') {
      btn.textContent = 'Обработка платежа…';
      await sleep(1600);
      await api(`/api/order/${order.id}/pay/test`, { method: 'POST', body: '{}' });
      clearCart();
      location.hash = '#/success/' + order.id;
      return;
    }
    const res = await api(`/api/order/${order.id}/pay/${order.payment_method}`, { method: 'POST', body: '{}' });
    if (res.confirmation_url || res.pay_url) {
      $('#pay-note').textContent = 'Откроется страница оплаты. После оплаты заказ обновится автоматически.';
      window.open(res.confirmation_url || res.pay_url, '_blank');
      pollPaid(order.id, btn);
    } else if (res.message) {
      $('#pay-note').textContent = res.message;
      btn.textContent = 'Ожидаем подтверждения…';
      pollPaid(order.id, btn);
    }
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false; btn.textContent = 'Перейти к оплате';
  }
}

async function pollPaid(orderId, btn) {
  for (let i = 0; i < 90; i++) {
    await sleep(2500);
    try {
      const o = await api('/api/order/' + orderId);
      if (o.status === 'paid') { clearCart(); location.hash = '#/success/' + orderId; return; }
    } catch (e) {}
  }
  if (btn) { btn.disabled = false; btn.textContent = 'Проверить ещё раз'; }
  $('#pay-note').textContent = 'Оплата ещё не поступила. Если вы оплатили — нажмите «Проверить ещё раз».';
}

function clearCart() { S.cart = {}; saveCart(); renderCount(); }

async function renderSuccess(orderId) {
  let o = null;
  try { o = await api('/api/order/' + orderId); } catch (e) {}
  if (!o) { $('#view').innerHTML = '<div class="empty">Заказ не найден</div>'; return; }
  const paid = o.status === 'paid';
  $('#view').innerHTML = `
  <div class="pay-wrap"><div class="pay-card">
    <div style="font-size:56px">${paid ? '✅' : '⏳'}</div>
    <h2 style="margin:6px 0">${paid ? 'Заказ оплачен!' : 'Заказ создан'}</h2>
    <div class="hint">${esc(o.id)} • ${fmt(o.total)}</div>
    <div class="hint mt">${esc(o.delivery.label)} • ${STATUS[o.status] || o.status}</div>
    <button class="btn primary mt" onclick="location.hash='#/catalog'">Вернуться в каталог</button>
    <button class="btn ghost" onclick="location.hash='#/orders'">Мои заказы</button>
  </div></div>`;
}

/* ---------------- заказы ---------------- */
function renderOrdersShell() {
  return `<div class="sect"><h2>Мои заказы</h2><div id="orders-list"><div class="empty">Загружаем…</div></div></div>`;
}
async function loadOrders() {
  try {
    const orders = await api('/api/orders');
    $('#orders-list').innerHTML = orders.length ? orders.map(o => `
      <div class="order-row">
        <div class="order-head"><b>${esc(o.id)}</b><span class="status ${esc(o.status)}">${STATUS[o.status] || esc(o.status)}</span></div>
        <div class="hint">${o.items.map(i => esc(i.name) + ' × ' + i.qty).join(', ')}</div>
        ${o.delivery && o.delivery.tracking ? `<div class="hint" style="margin-top:6px">📦 Трек: <b>${esc(o.delivery.tracking)}</b></div>` : ''}
        <div class="hint" style="margin-top:6px">${esc(o.created_at.slice(0, 10))} • ${esc(o.delivery.label)} • <b>${fmt(o.total)}</b></div>
      </div>`).join('') : '<div class="empty">Заказов пока нет 😔</div>';
  } catch (e) {
    $('#orders-list').innerHTML = '<div class="empty">Не удалось загрузить заказы</div>';
  }
}

/* ---------------- статические ---------------- */
function renderStatic(title, text) {
  return `<div class="page"><h1>${title}</h1><div class="panel">${esc(text || '').replace(/\n/g, '<br>') || 'Раздел наполняется в админ-панели.'}</div></div>`;
}

/* ---------------- тосты ---------------- */
function toast(msg, err) {
  const el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 2800);
}

/* ---------------- старт ---------------- */
document.addEventListener('click', e => {
  if (e.target.id === 'cart-btn') location.hash = '#/cart';
});
document.addEventListener('DOMContentLoaded', () => {
  const el = document.createElement('div');
  el.id = 'toasts';
  document.body.appendChild(el);
});

async function init() {
  try {
    const cfg = await api('/api/config');
    S.config = cfg;
    S.delivery = cfg.delivery_methods || {};
    $('#brand-name').textContent = cfg.shop_name;
    $('#foot-brand').textContent = cfg.shop_name;
    $('#foot-contacts').textContent = (cfg.texts && cfg.texts.contacts) || '';
    document.title = cfg.shop_name + ' — интернет-магазин';
    // полоса объявления
    var ann = (cfg.announcement || '').trim();
    var annBar = $('#ann-bar');
    if (ann && annBar) {
      annBar.classList.remove('hidden');
      $('#ann-text').textContent = ann;
    }
    // соцсети в футере
    var soc = cfg.social_links || {};
    var row = $('#foot-soc');
    if (row && (soc.tg || soc.vk || soc.wa || soc.ok || soc.ig)) {
      $('#foot-social-wrap').classList.remove('hidden');
      var icons = { tg: '✈️', vk: '🅥', wa: '💬', ok: '🟠', ig: '📸' };
      row.innerHTML = Object.entries(soc).filter(x => x[1]).map(function (x) {
        return '<a class="soc" href="' + esc(x[1]) + '" target="_blank" rel="noopener">' + (icons[x[0]] || '🔗') + '</a>';
      }).join('');
    }
  } catch (e) {}
  try {
    const cat = await api('/api/catalog');
    S.catalog = cat.products || [];
    S.categories = cat.categories || [];
  } catch (e) { toast('Не удалось загрузить каталог', true); }
  Object.keys(S.cart).forEach(id => { if (!S.catalog.find(p => p.id == id)) delete S.cart[id]; });
  saveCart(); renderCount();
  router();
}
window.addEventListener('hashchange', router);
init();
