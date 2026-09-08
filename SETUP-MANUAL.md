# Полная инструкция по настройке системы

## 1. Режимы

- **demo**: credentials не нужны, работают stub/dry-run.
- **staging**: отдельная база, HTTPS и тестовые аккаунты площадок.
- **production**: только после ручного approval всех gates.

## 2. Базовый запуск

```bash
python3 -m pytest -q tests
python3 -m py_compile telegram-shop/api.py telegram-shop/store.py marketing_adapters.py
./deploy/preflight-validation.sh
```

## 3. Secrets

Скопировать `staging.env.example` в secret manager VPS и заполнить значения на сервере. Не добавлять `.env` в Git, URL, frontend, APK, README или screenshots.

Обязательные группы:

- `CONTENT_CALLBACK_SECRET` для HMAC video callback;
- token и account ID каждой площадки, которая подключается.

## 4. Content pipeline

```text
POST /api/content/jobs
POST /api/content/jobs/{id}/claim
POST /api/content/jobs/{id}/result
POST /api/content/jobs/{id}/approve
```

При secret callback подпись считается HMAC-SHA256 по canonical JSON. Сначала проверить success, failure, duplicate callback и invalid signature на staging.

## 5. Campaign Manager

```text
POST /api/marketing/campaigns
POST /api/marketing/campaigns/{id}/prepare
POST /api/marketing/campaigns/{id}/approve
POST /api/marketing/campaigns/{id}/dry-run
GET  /api/marketing/campaigns/{id}/attribution
```

Реальная отправка запрещена до manual approval и provider staging test.

## 6. OAuth и adapters

Для каждой площадки вручную:

1. Создать приложение в официальном кабинете.
2. Настроить callback URL на HTTPS staging host.
3. Запросить минимальные scopes.
4. Авторизовать отдельный тестовый аккаунт.
5. Сохранить token только в secret manager.
6. Проверить `validate()` и `diagnostics()`.
7. Выполнить одну dry-run и одну staging publication.
8. Сохранить external ID и response без secrets.
9. Проверить rate limit и retry.

Scraping и browser automation запрещены.

## 7. Wildberries

До завершения seller/API audit оставить publishing disabled. Проверить account permissions, карточки, цены, остатки, заказы, rate limits и официальные endpoint-ы.

## 8. SEO

Проверить по HTTPS staging:

```text
/robots.txt
/sitemap.xml
```

Проверить metadata, canonical, Open Graph, JSON-LD, 404, mobile rendering и Core Web Vitals. После production deployment добавить сайт в Yandex Webmaster и Google Search Console и запросить переобход.

## 9. Deployment gate

Перед release:

```bash
./deploy/preflight-validation.sh
./deploy/env-preflight.sh
./deploy/secret-scan.sh
./deploy/https-preflight.sh https://staging.example.com
```

Перед rollback:

```bash
./deploy/rollback-preflight.sh /path/to/backup.sqlite
```

Restore и production backup выполнять только вручную в согласованное окно.
