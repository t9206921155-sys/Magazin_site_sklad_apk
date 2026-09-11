/* Блок 27 (CSP): «Стать продавцом» — бывший inline-скрипт become_seller.html. */
(function () {
  var btn = document.getElementById('sf-submit');
  if (!btn) return;
  btn.addEventListener('click', async function () {
    var note = document.getElementById('sf-note');
    var name = document.getElementById('sf-name').value.trim();
    var phone = document.getElementById('sf-phone').value.trim();
    if (name.length < 2) { note.textContent = '❌ Укажите название магазина'; note.style.color = '#ef4444'; return; }
    if (phone.length < 6) { note.textContent = '❌ Укажите телефон'; note.style.color = '#ef4444'; return; }
    btn.disabled = true; note.textContent = 'Создаём витрину…'; note.style.color = '';
    try {
      var res = await fetch('/api/seller/register', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ store_name: name, phone: phone, email: document.getElementById('sf-email').value, slug: document.getElementById('sf-slug').value, description: document.getElementById('sf-desc').value }),
      });
      var data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка');
      note.innerHTML = data.status === 'active'
        ? '✅ Витрина создана!<br><b>Ваш ключ доступа:</b> <code>' + data.key + '</code><br><b>Витрина:</b> <a href="/seller/' + data.slug + '">/seller/' + data.slug + '</a><br><a href="/seller/">Открыть личный кабинет продавца</a>'
        : '✅ Заявка принята! Мы подтвердим витрину и свяжемся с вами.';
      note.style.color = '#10b981';
    } catch (err) {
      note.textContent = '❌ ' + err.message;
      note.style.color = '#ef4444';
    }
    btn.disabled = false;
  });
})();
