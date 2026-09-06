# ТЗ — Content Hub, AI-видео и кампании

## 1. Назначение

Content Hub — единая точка подготовки контента товара для социальных сетей и marketplace-каналов. Он не публикует автоматически без ручного подтверждения.

## 2. Ограничения VPS

Текущий тестовый VPS: 1 vCPU, 1 GB RAM, 10 GB SSD. Локальный AI и ffmpeg на нём не запускать. VPS хранит только очередь, статусы и ссылки. Генерация выполняется внешним AI/video worker. Фолбэк — лёгкий slideshow.

## 3. Сущности

- `content_packages`: контент товара и версии;
- `content_jobs`: задачи AI/render;
- `campaigns`: кампании и каналы;
- `campaign_publications`: попытки публикаций;
- `content_approvals`: approve/reject;
- `content_costs`: provider, usage, cost;
- `content_audit`: полная история.

## 4. Безопасность

- ключи AI и соцсетей только backend;
- OAuth с ротацией;
- проверка прав на фото и музыку;
- ComplianceAgent перед review;
- ручной approve;
- rate limit и cost limit;
- секреты никогда не попадают в frontend, APK и screenshots.

## 5. Приоритет реализации

1. Content package и preview.
2. Очередь задач и fallback slideshow.
3. Telegram/VK/Avito adapters.
4. CRM approve/reject.
5. Instagram/TikTok official APIs.
6. Wildberries после подтверждения официального API.

## 6. Что не делать

Не использовать scraping, обход ограничений площадок, автоматизацию личных аккаунтов и автопубликацию без approve.
