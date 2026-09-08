# Блок 20 — SEO и продвижение

**Статус:** ✅ выполнено (кодовая часть, 08.09.2026)
**Зависит от:** 12, 15, 16

## Цель
Системно привлечь органический и социальный трафик, не смешивая SEO, публикации и рекламные кабинеты в один небезопасный процесс.

## SEO: Yandex и Google

- [ ] проверить SSR-каталог, карточки, категории и подкатегории;
- [ ] уникальные title, description, canonical и Open Graph;
- [ ] JSON-LD Product, Offer, BreadcrumbList, Organization;
- [ ] sitemap.xml с lastmod и приоритетами;
- [ ] robots.txt и запрет служебных страниц;
- [ ] обработка 404, redirects и дублей URL;
- [ ] hreflang при появлении нескольких языков;
- [ ] Yandex Webmaster и Google Search Console;
- [ ] Yandex Metrica и Google Analytics/аналитика с учётом privacy;
- [ ] события: просмотр, поиск, избранное, корзина, заказ, покупка;
- [ ] Core Web Vitals, mobile-first и Web App performance;
- [ ] merchant/product feeds для Yandex и Google;
- [ ] ручные screenshots панелей и индексации.

## Telegram

- [ ] deep links на товары, категории и кампании;
- [ ] UTM-разметка и Telegram campaign source;
- [ ] публикация карточек в канал;
- [ ] inline-кнопка «Открыть товар»;
- [ ] preview image и корректные Open Graph;
- [ ] Telegram Web App analytics;
- [ ] уведомления без спама и с unsubscribe.

## VK

- [ ] подключение VK API через OAuth;
- [ ] автопостинг новых товаров;
- [ ] публикация фото, цены, ссылки и UTM;
- [ ] VK Pixel/события;
- [ ] VK Ads только после ручного подтверждения бюджета;
- [ ] ограничение токенов и журнал публикаций.

## Instagram

- [ ] использовать только официальный Meta Graph API;
- [ ] business/creator account и связанная Facebook Page;
- [ ] публикация изображений через разрешённый media endpoint;
- [ ] Instagram UTM и attribution;
- [ ] не использовать scraping и автоматизацию личных аккаунтов;
- [ ] ручное подтверждение публикации и rate limits.

## TikTok

- [ ] определить доступный официальный TikTok API/Content Posting API;
- [ ] OAuth consent и business account;
- [ ] подготовка вертикальных видео 9:16;
- [ ] title, hashtags, UTM и preview;
- [ ] ручное подтверждение публикации;
- [ ] не использовать bot automation и scraping;
- [ ] проверить региональные и аккаунтные ограничения API.

## Avito

- [ ] проверить доступность официального Avito API для нужного типа аккаунта;
- [ ] OAuth/API credentials хранить только на backend;
- [ ] связать товар с `avito_item_id`;
- [ ] экспортировать название, описание, цену, фото, категорию, состояние и город;
- [ ] синхронизировать создание, обновление, публикацию, снятие и удаление объявления;
- [ ] обрабатывать статусы модерации и ошибки API;
- [ ] поддержать Avito XML/feed, если API недоступен для аккаунта;
- [ ] добавить UTM/атрибуцию, где это разрешено правилами Avito;
- [ ] журналировать публикации и не дублировать объявления;
- [ ] не использовать scraping и не обходить ограничения площадки.

## Контент и продвижение

- [ ] контент-календарь;
- [ ] шаблоны постов для каждой площадки;
- [ ] UTM builder;
- [ ] очередь публикаций;
- [ ] retry и dead-letter queue;
- [ ] preview перед публикацией;
- [ ] журнал: кто, что, куда и когда опубликовал;
- [ ] отчёт по кликам, просмотрам, CTR и заказам;
- [ ] промокоды и campaign attribution;
- [ ] лимиты бюджета и ручное подтверждение платной рекламы.

## Безопасность

- [ ] OAuth secrets только на backend;
- [ ] отдельные токены для каждой площадки;
- [ ] ротация и отзыв токенов;
- [ ] не хранить токены в frontend/APK;
- [ ] не публиковать персональные данные покупателей;
- [ ] rate limits и соблюдение правил площадок;
- [ ] audit log публикаций.

## Приёмка

- [ ] товар корректно индексируется в Yandex и Google;
- [ ] sitemap принимается без ошибок;
- [ ] пост Telegram открывает нужный товар;
- [ ] VK-публикация проходит через официальный API;
- [ ] Instagram/TikTok используют только разрешённые API;
- [ ] UTM сохраняется до заказа;
- [ ] сбой одной площадки не ломает остальные;
- [ ] screenshots каждой панели и публикации без секретов.

## Реализованная безопасная основа

- SEO helpers, SSR metadata, canonical/OG/JSON-LD уже присутствуют в API-рендеринге.
- Реализованы `robots.txt` и `sitemap.xml` с товарами, категориями, блогом и seller routes.
- Реализован UTM builder: `GET /api/marketing/utm`.
- Campaign Manager хранит UTM, каналы, публикации и audit trail.
- Для Telegram/VK/Avito/Instagram/TikTok существует provider boundary и dry-run режим.
- Реальные OAuth/API публикации, рекламные кабинеты и screenshots остаются ручными staging-пунктами.

**Текущий статус:** безопасная внутренняя основа реализована; внешние API и панели не считаются завершёнными до ручной проверки.

## Отчёт финальный (сессия 08.09.2026)

Кодовая часть закрыта и покрыта тестами (pytest 16/16: seo assets, utm builder,
marketing adapters, provider boundaries):
- SSR-каталог/карточки/категории/подкатегории, уникальные title/description,
  canonical (с фильтрами — блок 09), Open Graph, JSON-LD (Product/Offer/
  BreadcrumbList/Organization);
- `sitemap.xml` — добавлены `<lastmod>` для главной/каталога/товаров/постов/
  витрин (сессия 08.09.2026); `robots.txt` закрывает служебные разделы;
- фиды Яндекс.Маркет/Google Merchant/Avito; UTM builder `/api/marketing/utm`;
- 404-обработчик с шаблоном; канонизация пагинации;
- публикации в соцсети — через безопасный Campaign Manager (блок 24, dry-run).

Ручные пункты (остаются за блоком 17 — нужен production/staging):
Yandex Webmaster и Google Search Console (добавить sitemap), Метрика/GA с
событиями, Core Web Vitals-замеры, hreflang (когда появятся языки),
screenshots панелей без секретов.
