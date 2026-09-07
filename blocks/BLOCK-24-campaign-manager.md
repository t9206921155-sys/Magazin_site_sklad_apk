# Блок 24 — Campaign Manager и публикация

**Статус:** ⏳ запланировано

## Цель
Публиковать один подтверждённый контент-пакет в Telegram, VK, Avito, Instagram и TikTok через независимые adapters.

## Кампания

- [ ] campaign name, products, dates, UTM;
- [ ] channels and per-channel settings;
- [ ] budget and publication limits;
- [ ] content preview;
- [ ] statuses draft/review/approved/published/failed;
- [ ] approve/reject with comment;
- [ ] audit log;
- [ ] retry и dead-letter queue;
- [ ] статистика views/clicks/CTR/orders.

## Adapters

- [ ] Telegram deep links and channel posts;
- [ ] VK official API;
- [ ] Avito official API/feed;
- [ ] Instagram official Meta Graph API;
- [ ] TikTok official Content Posting API;
- [ ] Wildberries only after official API/account audit.

## Правила

- [ ] OAuth secrets только backend;
- [ ] не использовать scraping;
- [ ] публикация только после approve;
- [ ] сбой одного канала не ломает остальные;
- [ ] UTM сохраняется до заказа;
- [ ] ручное подтверждение рекламного бюджета.

## Приёмка

- [ ] одна кампания создаёт preview для всех выбранных каналов;
- [ ] один канал может упасть без отмены остальных;
- [ ] повторная отправка не создаёт дубль;
- [ ] публикация и результат видны в CRM;
- [ ] screenshots кампании и публикаций без секретов.

## Отчёт (текущий этап)

- Добавлены сущности campaigns и campaign_publications.
- Добавлены API создания и списка кампаний.
- Добавлена подготовка публикаций по каналам Telegram, VK, Avito, Instagram, TikTok и Wildberries.
- Добавлена история публикаций и статусы draft/approved/published/failed/rejected.
- В CRM добавлен интерфейс создания кампании и подготовки публикации.
- Реальные adapters социальных сетей подключаются после получения официальных credentials и проверки API.
