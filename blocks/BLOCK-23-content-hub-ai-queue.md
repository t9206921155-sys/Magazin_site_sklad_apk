# Блок 23 — Content Hub и AI Video Queue

**Статус:** ⏳ запланировано
**Приоритет:** P0 для продвижения

## Цель
Создать единый контент-пакет товара и очередь генерации, не перегружая VPS тяжёлым AI/ffmpeg.

## Архитектура

VPS хранит карточку, задачу, статусы и метаданные. AI/video worker работает внешне или на отдельном worker-сервере. Результаты сохраняются в Object Storage.

## Content package

- [ ] title, short_text, long_text;
- [ ] hashtags, CTA, UTM;
- [ ] preview image;
- [ ] video 9:16, 1:1, 16:9;
- [ ] исходные фото и версия prompt;
- [ ] provider, стоимость, длительность, error;
- [ ] consent/rights metadata.

## Queue state machine

```text
draft → queued → processing → review → approved → published
                              ↘ failed → retry
```

- [ ] таблица `content_jobs`;
- [ ] idempotency key;
- [ ] max retries;
- [ ] дневной лимит задач и стоимости;
- [ ] ручной retry;
- [ ] отмена задачи;
- [ ] отсутствие блокировки API при генерации.

## Agents/adapters

- [ ] ContentCopyAgent;
- [ ] VideoStoryboardAgent;
- [ ] MediaRenderWorker;
- [ ] ComplianceAgent;
- [ ] AI provider adapter;
- [ ] fallback slideshow без AI;
- [ ] ручное approve перед публикацией.

## Приёмка

- [ ] AI provider недоступен — задача получает `failed`, магазин продолжает работать;
- [ ] fallback создаёт slideshow;
- [ ] готовый ролик доступен через Object Storage;
- [ ] стоимость и provider видны менеджеру;
- [ ] screenshots draft/review/approved.
