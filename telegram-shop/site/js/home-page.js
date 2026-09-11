/* Блок 27 (CSP): главная — бывший inline-скрипт home.html (слайдер + табы). */
(function () {
  var slides = document.querySelectorAll('#main-slider .slide');
  var dots = document.querySelectorAll('#main-slider .sl-dot');
  if (slides.length) {
    var cur = 0, timer = null;
    function go(i) {
      cur = (i + slides.length) % slides.length;
      slides.forEach(function (s, k) { s.classList.toggle('active', k === cur); });
      dots.forEach(function (d, k) { d.classList.toggle('active', k === cur); });
    }
    function start() { timer = setInterval(function () { go(cur + 1); }, 6000); }
    function restart() { clearInterval(timer); start(); }
    dots.forEach(function (d) {
      d.addEventListener('click', function () { go(+d.dataset.dot); restart(); });
    });
    var sl = document.getElementById('main-slider');
    var x0 = null;
    sl.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; });
    sl.addEventListener('touchend', function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 40) { go(cur + (dx < 0 ? 1 : -1)); restart(); }
      x0 = null;
    });
    start();
  }
  var tabs = document.querySelectorAll('.tabs .tab');
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      tabs.forEach(function (x) { x.classList.remove('active'); });
      t.classList.add('active');
      document.querySelectorAll('.tab-panel').forEach(function (p) { p.classList.remove('active'); });
      var panel = document.getElementById('tab-' + t.dataset.tab);
      if (panel) panel.classList.add('active');
    });
  });
})();
