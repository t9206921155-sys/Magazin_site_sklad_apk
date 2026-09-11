/* Блок 27 (CSP): общий JS SSR-страниц — бывший inline-скрипт base.html. */
// корзина на SSR-страницах: тот же localStorage, что и в Mini App/SPA
(function () {
  var CART_KEY = 'tgshop_cart';
  function load() { try { return JSON.parse(localStorage.getItem(CART_KEY) || '{}'); } catch (e) { return {}; } }
  function save(c) { localStorage.setItem(CART_KEY, JSON.stringify(c)); }
  function count() { var c = load(), n = 0; for (var k in c) n += c[k]; return n; }
  function render() { var el = document.getElementById('cart-count'); if (el) el.textContent = count(); }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-add]');
    if (!btn) return;
    var c = load();
    c[btn.dataset.add] = (c[btn.dataset.add] || 0) + 1;
    save(c); render();
    btn.textContent = '✓';
    setTimeout(function () { btn.textContent = '＋'; }, 900);
  });
  render();
})();
// мобильное меню
var burgerEl = document.getElementById('burger');
if (burgerEl) burgerEl.addEventListener('click', function () {
  document.getElementById('nav').classList.toggle('open');
});
// подписка на рассылку
var subFormEl = document.getElementById('sub-form');
if (subFormEl) subFormEl.addEventListener('submit', async function (e) {
  e.preventDefault();
  var note = document.getElementById('sub-note');
  note.style.color = '';
  note.textContent = 'Подписываем…';
  try {
    var res = await fetch('/api/subscribe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: document.getElementById('sub-email').value }),
    });
    var data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка');
    note.textContent = data['new'] ? '✅ Вы подписаны! Добро пожаловать в клуб выгодных покупок.'
                                  : '✅ Этот email уже подписан — спасибо!';
    note.style.color = '#10b981';
    document.getElementById('sub-email').value = '';
  } catch (err) {
    note.textContent = '❌ ' + err.message;
    note.style.color = '#ef4444';
  }
});
// недавно просмотренные товары
(function () {
  var pid = document.body.dataset.productId;
  if (pid) {
    var key = 'tgshop_recent';
    var seen = JSON.parse(localStorage.getItem(key) || '[]');
    var id = +pid;
    seen = seen.filter(function (x) { return x !== id; });
    seen.unshift(id);
    localStorage.setItem(key, JSON.stringify(seen.slice(0, 12)));
  }
})();
