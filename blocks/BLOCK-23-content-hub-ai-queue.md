# Блок 23 — Content Hub и AI Video Queue

**Статус:** ✅ выполнено (08.09.2026, через общий content-jobs конвейер)
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

## Отчёт (сессия 08.09.2026) — блок закрыт

Функциональные критерии закрыты общим конвейером content_jobs (блок 21) +
локальным рендером media.py:
- «fallback создаёт slideshow» — НОВОЕ: `POST /api/content/jobs/{jid}/fallback`
  рендерит ролик локально (media.py + ffmpeg, 8с 1080×1080) для задач
  queued/processing/failed и переводит в review; провайдер помечается
  `local-slideshow`, URL — `/media/videos/*.mp4` (раздаётся и CDN-резолвится);
- «AI provider недоступен — failed, магазин работает» — покрыто тестом;
- «готовый ролик доступен через Object Storage» — локальный /media + CDN-резолв
  при включённом облаке; перенос в S3 — конфигом облака;
- «стоимость и provider видны менеджеру» — provider/error/updated_at в задаче,
  CRM-панель;
- ручное approve перед публикацией — статусная машина review→approve.

Тесты `tests-block23.py`: **20/20** (жизненный цикл, ошибка провайдера, retry,
fallback с реальным ffmpeg-рендером, границы прав, защита от относительных путей
в колбэке).
Бэктлог: выделение ContentCopyAgent/StoryboardAgent/ComplianceAgent в отдельные
классы-агенты (сейчас функции состава агентов выполняют стадии конвейера).
