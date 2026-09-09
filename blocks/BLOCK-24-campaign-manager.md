# Блок 24 — Campaign Manager и публикация

**Статус:** ✅ выполнено (08.09.2026, безопасный MVP)

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

## Demo/staging workflow completed

- Bulk prepare creates one draft publication per configured channel with deduplication.
- Bulk approve changes only draft records to approved.
- Bulk dry-run returns deterministic stub results without external network calls.
- CRM exposes prepare-all, approve-all, dry-run and publication queue controls.

## Отчёт финальный (сессия 08.09.2026)

Тесты: pytest `test_marketing_adapters.py`, `test_provider_boundaries.py` —
16/16 вместе с SEO-тестами.
- Campaigns + publication records + lifecycle (draft/approved/published/failed/rejected).
- Bulk prepare (по одному draft на канал, дедупликация), bulk approve (только draft),
  bulk dry-run (детерминированные заглушки без сети) — покрыто тестами.
- UTM хранится в кампании и проставляется через UTM builder; сбой одного канала
  не ломает остальные (adapter boundary, dry-run контракт).
- Реальные transport-адаптеры Telegram/VK/Avito/Instagram/TikTok/WB остаются
  выключенными до staging-credentials и ручного approve (внешние условия, блок 17).
