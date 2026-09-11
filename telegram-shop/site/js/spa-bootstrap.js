/* Блок 27 (CSP): SPA-оболочка /shop — бывший inline-скрипт site/index.html. */
(function () {
  var burgerEl = document.getElementById('burger');
  if (burgerEl) burgerEl.addEventListener('click', function () {
    document.getElementById('nav').classList.toggle('open');
  });
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
})();
