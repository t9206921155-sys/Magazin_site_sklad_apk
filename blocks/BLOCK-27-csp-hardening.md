# Блок 27 — CSP-закалка: вынос inline-JS и Content-Security-Policy

**Статус:** ✅ выполнено
**Сессия:** 11.09.2026
**Зависит от:** 15 (развитие security-заголовков; закрывает CSP-бэклог блока 15)
**Оценка:** 0,3–0,5 сессии · Фактически: одна сессия совместно с блоком 25 Ф1

---

## Цель

Закрыть бэклог блока 15 («CSP — нужен вынос inline-скриптов фронтов»): убрать
inline-скрипты с публичных SSR-страниц и включить строгий
`Content-Security-Policy` с `script-src 'self'` (без `unsafe-inline`) там, где
это безопасно, не сломав внутренние инструменты.

## Задачи

- [x] Инвентаризация inline-JS: публичный сайт (site/templates — 8 файлов,
      11 блоков, 2 onclick) / SPA `/shop` (1 bootstrap) / внутренние инструменты
      (webapp, warehouse, admin, crm, seller — только inline-обработчики в HTML).
- [x] Вынос всех inline-скриптов публичного сайта в `site/js/*.js` (9 файлов,
      `/site/…` раздаётся как статика, попадает под кэш-заголовки):
      `page-common` (base: корзина/бургер/подписка/недавно-смотрел),
      `product-page` (чат+избранное+отзыв+покупка+рекомендации),
      `home-page`, `catalog-page`, `favorites-page`, `become-seller`,
      `android-download`, `android-rustore`, `spa-bootstrap` (/shop), `app-download` (блок 25).
- [x] Данные из Jinja перенесены из JS в data-атрибуты: `<body data-product-id …
      data-seller-id>` (product.html), `data-recommended` (android_download.html,
      app_download.html) — JS больше не содержит серверных вставок.
- [x] onclick-обработчики карточки товара заменены на `id` + `addEventListener`
      (`chat-close-btn`, `chat-send-btn`).
- [x] CSP-мидлварь в `api.py` (расширение `security_headers` блока 15):
      - **строгий `Content-Security-Policy`** для публичных SSR-документов:
        `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
        img-src 'self' data: blob: https:; font-src 'self' data:;
        connect-src 'self' https: wss:; media-src 'self' blob:;
        object-src 'none'; base-uri 'self'; form-action 'self'`;
      - **Report-Only** (`Content-Security-Policy-Report-Only`) для поверхностей
        с inline-обработчиками: `/app` (Mini App + telegram.org script),
        `/warehouse`, `/admin`, `/crm`, `/shop`, `/seller` (кабинет), `/api/*` и статика;
      - заголовок ставится только для `text/html` ответов.
- [x] Тесты `tests-block27.py` (86 проверок): CSP на 8 публичных страницах,
      отсутствие inline `<script>`/`onclick` в HTML, подключение внешних JS,
      сохранность JSON-LD, Report-Only на внутренних инструментах, строгий CSP
      на публичной витрине продавца, живость API.
- [x] Подключение в `run-tests.sh` (перед block15, который остаётся последним).

## Отчёт

- Прогон 11.09.2026: **tests-block27.py 86/86**; полная регрессия зелёная
  (см. отчёт блока 25; block14 29/32 — pre-existing на чистом `main`, не связан;
  исправлено 12.09.2026 — см. «Фикс теста» в отчёте блока 14).
- JSON-LD (`<script type="application/ld+json">`) сохранён: CSP не блокирует
  неисполняемые data-блоки.
- Telegram Mini App (`/app`) требует внешний скрипт `telegram.org` и inline-обработчики
  складского PWA — для них CSP работает в режиме **Report-Only** и ничего не ломает;
  их перевод в строгий режим — бэктлог (требует выноса обработчиков warehouse/crm).

## Критерий закрытия бэклога блока 15

✅ CSP включён для всего публичного периметра (витрина, каталог, карточка,
страницы загрузки, блог, privacy); внутренние инструменты — под наблюдением
Report-Only с тем же политиком.
