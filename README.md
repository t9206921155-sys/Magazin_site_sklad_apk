# Magazin_site_sklad_apk

Монорепозиторий проекта **Telegram Shop**: маркетплейс/интернет-магазин с SEO-сайтом,
Telegram-ботом и Mini App, админкой, мобильным складом (PWA/APK), интеграциями доставок,
оплатой, 1С и ИИ-инструментами.

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

- `telegram-shop/apk/Sklad-1.0.5-release.apk`
- `telegram-shop/aab/Sklad-1.0.5-release.aab`

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
- `telegram-shop/FINAL-RELEASE-HANDOFF.md` — сводный handoff по релизу Android 1.0.5
- `telegram-shop/scripts/post_deploy_smoke_check.sh` — быстрый smoke-check production-домена
- `telegram-shop/scripts/merge_feature_to_main.sh` — helper script для merge feature-ветки в `main`
- `telegram-shop/scripts/release_status.sh` — быстрый вывод статуса релиза, версий и SHA-256
- `telegram-shop/PLAN.md` — развитие платформы
- `telegram-shop/MARKETPLACE-PLAN.md` — дорожная карта маркетплейса
- `telegram-shop/AUDIT.md` — аудит функционала

## Рекомендация по git

Рабочие изменения лучше вести через feature-ветки, а затем вливать в `main` после проверки.
