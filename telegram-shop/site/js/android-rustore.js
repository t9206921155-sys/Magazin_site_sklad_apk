/* Блок 27 (CSP): /download/android/rustore — бывший inline-скрипт android_rustore.html. */
(function () {
  var feedback = document.getElementById('copy-feedback');
  if (!feedback) return;
  document.querySelectorAll('[data-copy-target]').forEach(function (btn) {
    btn.addEventListener('click', async function () {
      var field = document.getElementById(btn.dataset.copyTarget);
      var text = field ? field.value : '';
      try {
        await navigator.clipboard.writeText(text);
        feedback.textContent = '✅ Поле скопировано';
        feedback.style.color = '#10b981';
      } catch (e) {
        feedback.textContent = '❌ Не удалось скопировать';
        feedback.style.color = '#ef4444';
      }
    });
  });
})();
