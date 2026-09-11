/* Блок 27 (CSP): каталог — бывший inline-скрипт catalog.html (поиск с подсказками). */
(function () {
  var input = document.getElementById('cat-search');
  var box = document.getElementById('suggest-box');
  if (!input || !box) return;
  var timer = null;
  input.addEventListener('input', function () {
    clearTimeout(timer);
    var q = input.value.trim();
    if (q.length < 2) { box.style.display = 'none'; return; }
    timer = setTimeout(function () {
      fetch('/api/search/suggest?q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var items = (d.suggestions || []).slice(0, 6);
          if (!items.length) { box.style.display = 'none'; return; }
          box.innerHTML = items.map(function (s) {
            return '<a class="suggest-item" href="/p/' + s.id + '">' +
              '<img src="' + s.photo + '" alt="">' +
              '<span>' + s.name.replace(/[<>&"]/g, '') + '</span>' +
              '<b>' + s.price + ' ₽</b></a>';
          }).join('');
          box.style.display = 'block';
        }).catch(function () {});
    }, 250);
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.search-form')) box.style.display = 'none';
  });
})();
