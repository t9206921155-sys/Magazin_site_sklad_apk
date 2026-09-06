# Блок 20 — SEO и продвижение

**Статус:** ⏳ запланировано
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
