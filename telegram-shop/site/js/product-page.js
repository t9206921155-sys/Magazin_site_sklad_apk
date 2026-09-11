/* Блок 27 (CSP): карточка товара — бывшие inline-скрипты product.html.
   Данные товара приходят через data-атрибуты <body> (data-product-id, data-seller-id). */
(function () {
  var PID = +(document.body.dataset.productId || 0);
  var SID = +(document.body.dataset.sellerId || 0);

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  /* ── Чат с продавцом ── */
  var panel = document.getElementById('chat-panel');
  var openBtn = document.getElementById('chat-open-btn');
  var closeBtn = document.getElementById('chat-close-btn');
  var sendBtn = document.getElementById('chat-send-btn');
  var guestKey = localStorage.getItem('tgshop_guest') ||
    (function () { var g = 'g-' + Date.now() + '-' + Math.random().toString(36).slice(2); localStorage.setItem('tgshop_guest', g); return g; })();

  async function loadChat() {
    var box = document.getElementById('chat-msgs');
    try {
      var res = await fetch('/api/chat/messages?product_id=' + PID + '&seller_id=' + SID + '&buyer_key=' + encodeURIComponent('g:' + guestKey) + '&guest_id=' + encodeURIComponent(guestKey));
      var ms = await res.json();
      box.innerHTML = ms.length ? ms.map(function (m) {
        return '<div style="align-self:' + (m.sender === 'seller' ? 'flex-end' : 'flex-start') + '; max-width:80%; padding:8px 12px; border-radius:12px; font-size:14px; background:' + (m.sender === 'seller' ? '#0F766E' : '#e5e7eb') + '; color:' + (m.sender === 'seller' ? '#fff' : '#111') + '">' + esc(m.text) + '<div style="font-size:10px; opacity:.7; margin-top:2px">' + (m.ts || '').slice(11, 16) + '</div></div>';
      }).join('') : '<div style="color:#888; font-size:13px; text-align:center">Здравствуйте! Задайте вопрос о товаре — продавец ответит здесь.</div>';
      box.scrollTop = 99999;
    } catch (e) { box.innerHTML = '<div style="color:#c33">Не удалось загрузить сообщения</div>'; }
  }
  function showChatPanel() { panel.style.display = 'flex'; loadChat(); openBtn.style.display = 'none'; }
  function closeChatPanel() { panel.style.display = 'none'; openBtn.style.display = ''; }
  async function sendChatMsg() {
    var inp = document.getElementById('chat-input');
    var text = inp.value.trim();
    if (!text) return;
    try {
      await fetch('/api/chat/send?guest_id=' + encodeURIComponent(guestKey), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: PID, seller_id: SID, text: text, buyer_name: 'Гость сайта' }),
      });
      inp.value = '';
      loadChat();
    } catch (e) {}
  }
  if (panel && openBtn) {
    openBtn.addEventListener('click', showChatPanel);
    if (closeBtn) closeBtn.addEventListener('click', closeChatPanel);
    if (sendBtn) sendBtn.addEventListener('click', sendChatMsg);
    // обратная совместимость: window.*-имя сохранено
    window.closeChatPanel = closeChatPanel;
    window.sendChatMsg = sendChatMsg;
  }

  /* ── Избранное (localStorage, синхронизируется со страницей /favorites) ── */
  (function () {
    var KEY = 'tgshop_fav';
    var btn = document.getElementById('fav-btn');
    if (!btn) return;
    function favs() { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; } }
    function save(list) { localStorage.setItem(KEY, JSON.stringify(list)); }
    function isFav() { return favs().some(function (f) { return f.id === btn.dataset.id; }); }
    window.toast = window.toast || function (msg) {
      var t = document.createElement('div');
      t.className = 'toast-msg';
      t.textContent = msg;
      document.body.appendChild(t);
      setTimeout(function () { t.remove(); }, 2200);
    };
    function render() {
      if (isFav()) { btn.textContent = '❤ В избранном'; btn.classList.add('active'); }
      else { btn.textContent = '❤ В избранное'; btn.classList.remove('active'); }
    }
    btn.addEventListener('click', function () {
      var list = favs();
      if (isFav()) {
        list = list.filter(function (f) { return f.id !== btn.dataset.id; });
        toast('Удалено из избранного');
      } else {
        list.push({ id: btn.dataset.id, name: btn.dataset.name, price: +btn.dataset.price, photo: btn.dataset.photo, at: Date.now() });
        toast('Добавлено в избранное ❤');
      }
      save(list);
      render();
    });
    render();
  })();

  /* ── Отзыв ── */
  var revForm = document.getElementById('rev-form');
  if (revForm) revForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    var f = new FormData(this);
    var note = document.getElementById('rev-note');
    note.textContent = 'Отправляем…';
    try {
      var res = await fetch('/api/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_id: PID,
          author: f.get('author') || 'Гость',
          rating: +f.get('rating'),
          text: f.get('text'),
        }),
      });
      var data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка');
      note.textContent = data.status === 'approved'
        ? '✅ Спасибо! Ваш отзыв опубликован.'
        : '✅ Спасибо! Отзыв отправлен на модерацию.';
      note.style.color = '#10b981';
      if (data.status === 'approved') setTimeout(function () { location.reload(); }, 1200);
    } catch (err) {
      note.textContent = '❌ ' + err.message;
      note.style.color = '#ef4444';
    }
  });

  /* ── Покупка с SSR-страницы + «вы недавно смотрели» ── */
  (function () {
    var CART_KEY = 'tgshop_cart';
    function load() { try { return JSON.parse(localStorage.getItem(CART_KEY) || '{}'); } catch (e) { return {}; } }
    function save(c) { localStorage.setItem(CART_KEY, JSON.stringify(c)); }
    document.addEventListener('click', function (e) {
      var buy = e.target.closest('[data-buy]');
      var now = e.target.closest('[data-buynow]');
      var t = buy || now;
      if (!t) return;
      var c = load();
      c[t.dataset.buy || t.dataset.buynow] = (c[t.dataset.buy || t.dataset.buynow] || 0) + 1;
      save(c);
      location.href = '/shop#/cart';
    });
    var key = 'tgshop_recent';
    var seen = JSON.parse(localStorage.getItem(key) || '[]');
    var me = PID;
    if (seen.length > 1) {
      var grid = document.getElementById('recent-grid');
      var ids = seen.filter(function (x) { return x !== me; }).slice(0, 4);
      if (ids.length && grid) {
        fetch('/api/recommendations/recent?ids=' + ids.join(',')).then(function (r) { return r.json(); }).then(function (data) {
          if (!data.products || !data.products.length) return;
          grid.innerHTML = data.products.map(function (r) {
            return '<article class="card"><a class="card-img" href="/p/' + r.id + '"><img src="' + r.photo + '" loading="lazy"></a>' +
              '<div class="card-body"><a class="card-name" href="/p/' + r.id + '">' + r.name + '</a>' +
              '<div class="card-foot"><div class="price"><span class="now">' + r.price + ' ₽</span></div>' +
              '<button class="add-btn" data-add="' + r.id + '">＋</button></div></div></article>';
          }).join('');
          document.getElementById('recent').style.display = '';
        });
      }
    }
  })();
})();
