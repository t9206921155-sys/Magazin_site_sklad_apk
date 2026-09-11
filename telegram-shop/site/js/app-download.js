/* Блок 25: страница /download/app — конфигуратор deep link и QR (CSP: внешний файл). */
(function () {
  var input = document.getElementById('server-url');
  if (!input) return;
  var linkCode = document.getElementById('deep-link-code');
  var serverCode = document.getElementById('server-url-code');
  var openConnect = document.getElementById('open-connect');
  var openSetup = document.getElementById('open-setup');
  var note = document.getElementById('copy-note');
  var qrConnect = document.getElementById('qr-connect');
  var qrSetup = document.getElementById('qr-setup');
  var qrConnectLink = document.getElementById('download-connect-qr');
  var qrSetupLink = document.getElementById('download-setup-qr');

  function normalizeUrl(raw) {
    raw = (raw || '').trim();
    if (!raw) return input.dataset.recommended || '';
    if (!/^https?:\/\//i.test(raw)) raw = 'https://' + raw;
    try {
      var u = new URL(raw);
      if (!u.pathname) u.pathname = '/';
      u.search = '';
      u.hash = '';
      return u.toString();
    } catch (e) {
      return raw;
    }
  }

  function refreshLinks() {
    var url = normalizeUrl(input.value);
    var connect = 'shop://connect?url=' + encodeURIComponent(url);
    var setup = 'shop://setup?url=' + encodeURIComponent(url);
    var connectQr = '/api/app/version/qr.svg?mode=connect&server=' + encodeURIComponent(url);
    var setupQr = '/api/app/version/qr.svg?mode=setup&server=' + encodeURIComponent(url);
    openConnect.href = connect;
    openSetup.href = setup;
    linkCode.textContent = connect;
    serverCode.textContent = url;
    qrConnect.src = connectQr;
    qrSetup.src = setupQr;
    qrConnectLink.href = connectQr;
    qrSetupLink.href = setupQr;
  }

  input.addEventListener('input', refreshLinks);
  refreshLinks();

  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', async function () {
      var el = document.getElementById(btn.dataset.copy);
      var text = el ? el.textContent : '';
      try {
        await navigator.clipboard.writeText(text);
        note.textContent = '✅ Скопировано';
        note.style.color = '#10b981';
      } catch (e) {
        note.textContent = '❌ Не удалось скопировать';
        note.style.color = '#ef4444';
      }
    });
  });
})();
