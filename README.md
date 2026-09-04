# Magazin_site_sklad_apk

[![Tests](https://github.com/t9206921155-sys/Magazin_site_sklad_apk/actions/workflows/tests.yml/badge.svg)](https://github.com/t9206921155-sys/Magazin_site_sklad_apk/actions/workflows/tests.yml)


Монорепозиторий проекта **Telegram Shop**: маркетплейс/интернет-магазин с SEO-сайтом,
Telegram-ботом и Mini App, админкой, мобильным складом (PWA/APK), интеграциями доставок,
оплатой, 1С и ИИ-инструментами.

---

> ## 📍 Начало работы над проектом
>
> | Файл | Зачем |
> |---|---|
> | **[`ROADMAP.md`](ROADMAP.md)** | Единый трекер: какой блок готов, какой нет. **Читать первым.** |
> | **[`SESSION-PLAYBOOK.md`](SESSION-PLAYBOOK.md)** | Как поднять окружение и синхронизироваться |
> | **[`blocks/`](blocks/)** | План и отчёт по каждому блоку работ |
>
> ⚠️ Полный клон весит 106 МБ. Для работы использовать лёгкий клон на 7 МБ —
> команда в `SESSION-PLAYBOOK.md`.

---

## Что внутри

| Путь | Назначение |
|---|---|
| `telegram-shop/` | Основной backend + SSR-сайт + админка + Telegram-логика + склад |
| `mobile/` | Отдельный каркас мобильного приложения |
| `deploy/` | Конфиги деплоя, nginx и helper-скрипт production rollout |
| `Dockerfile`, `docker-compose.yml` | Корневой запуск контейнеров |
| `site-preview.png` | Превью проекта для GitHub |

## Ключевые возможности

- SEO-сайт с каталогом, товарами, блогом и SSR
- Telegram-бот + Mini App
- Маркетплейс: продавцы, витрины, чат, рейтинг, офферы, безопасная сделка
- Мобильный склад: фото, штрих-коды, этикетки, публикация товара с телефона
- Админка: товары, заказы, продавцы, тарифы, аналитика, контент
- Интеграции: СДЭК, 5POST, Яндекс Доставка, ЮKassa, Т-Банк, CryptoBot, 1С
- ИИ-функции: описания, SEO, рекламные тексты, аналоги, баннеры и видео

## Текущее состояние

Проект включает магазин/Mini App, складской PWA/APK, мультисклад, роли, 1С, офлайн-очередь, печать ZPL/EPL/PDF, отчёты, каталог с фильтрами и CI. Поддерживаются режимы базы VPS/SQLite, VPS → Supabase, Direct Supabase и MySQL/MariaDB; фотографии можно хранить в S3-compatible storage или через Yandex Disk API.

Production-документация: [архитектура хранения](STORAGE-ARCHITECTURE.md), [ручная валидация](DEVELOPER-MANUAL-VALIDATION.md).

Оставшиеся работы и порядок реализации: [IMPLEMENTATION-QUEUE.md](IMPLEMENTATION-QUEUE.md).

Инструкция production-развёртывания: [PRODUCTION-SETUP.md](PRODUCTION-SETUP.md).

Для обычного API достаточно `requirements.txt`; обработку видео устанавливайте отдельно: `pip install -r requirements-video.txt`. Для CI и разработки: `pip install -r requirements-dev.txt`. После деплоя запускайте:

```bash
./deploy/post-deploy-smoke.sh https://YOUR-DOMAIN
```

Для авторизованных проверок задайте `WH_LOGIN` и `WH_PASSWORD` через окружение. План работ ведётся в [ROADMAP.md](ROADMAP.md), каждый блок описан в [blocks/](blocks/).

## Быстрый старт

```bash
cd telegram-shop
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

После запуска:

- `http://localhost:8000/` — сайт
- `http://localhost:8000/app` — Telegram Mini App
- `http://localhost:8000/admin` — админка
- `http://localhost:8000/warehouse` — мобильный склад
- `http://localhost:8000/seller` — кабинет продавца

## Docker

```bash
docker compose up -d --build
```

## APK / AAB / мобильный склад

Готовые артефакты:

- `telegram-shop/apk/Sklad-1.0.6-release.apk`
- `telegram-shop/aab/Sklad-1.0.6-release.aab`

Исходники Android-wrapper и сборка:

- `telegram-shop/apk-build/android/`
- `telegram-shop/apk-build/rebuild-apk.sh`
- `telegram-shop/apk-build/README-APK.md`
- `mobile/build-apk.sh`

## Документация по проекту

- `telegram-shop/README.md` — основное описание
- `telegram-shop/DEPLOY-CHECKLIST.md` — production-checklist релиза
- `telegram-shop/PROD-DEPLOY-QUICKSTART.md` — короткая инструкция деплоя под копипасту
- `telegram-shop/MERGE-READY-PLAN.md` — план подготовки ветки к merge в `main`
- `telegram-shop/MERGE-COMMAND-BLOCK.md` — точный блок команд для deploy + merge
- `telegram-shop/PR-MERGE-SUMMARY-RU.md` — готовое русскоязычное summary для PR / merge
- `telegram-shop/RUSTORE-CARD-CHECKLIST.md` — тексты и ассеты для RuStore
- `telegram-shop/FINAL-RELEASE-HANDOFF.md` — сводный handoff по релизу Android 1.0.6
- `telegram-shop/STEP-BY-STEP-RUNBOOK.md` — полная пошаговая инструкция по серверу, складу, APK, облаку и публикации
- `telegram-shop/FIRST-LAUNCH-15-MIN.md` — ультра-короткий сценарий первого запуска
- `telegram-shop/WAREHOUSE-EMPLOYEE-GUIDE.md` — простая инструкция для сотрудника склада
- `telegram-shop/OWNER-ADMIN-SETUP.md` — инструкция для владельца/админа с exact полями и порядком настройки
- `telegram-shop/SETTINGS-FIELD-MAP.md` — единая таблица «что куда вписывать» по .env, облаку, AI, VK, Avito и оплате
- `telegram-shop/APK-TEST-CHECKLIST.md` — чек-лист ручной проверки Android APK перед выдачей сотрудникам
- `telegram-shop/VPS-YANDEX-SETUP.md` — точная схема VPS + SQLite + Yandex Object Storage для фото и backup
- `telegram-shop/scripts/backup_sqlite_to_s3.py` — ручной/cron backup `shop.db` в S3/Yandex Object Storage
- `telegram-shop/scripts/post_deploy_smoke_check.sh` — быстрый smoke-check production-домена
- `telegram-shop/scripts/merge_feature_to_main.sh` — helper script для merge feature-ветки в `main`
- `telegram-shop/scripts/release_status.sh` — быстрый вывод статуса релиза, версий и SHA-256
- `telegram-shop/PLAN.md` — развитие платформы
- `telegram-shop/MARKETPLACE-PLAN.md` — дорожная карта маркетплейса
- `telegram-shop/AUDIT.md` — аудит функционала

## Рекомендация по git

Рабочие изменения лучше вести через feature-ветки, а затем вливать в `main` после проверки.
