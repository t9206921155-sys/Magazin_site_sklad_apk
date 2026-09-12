# Установка «из коробки» — авторазвёртывание Telegram Shop

Единая точка входа — **`./setup.sh`**. Три сценария ниже закрывают
локальный запуск, чистый VPS и обновление. Ручная настройка больше не
требуется: мастер сам создаёт `.env`, генерирует секреты, настраивает
Telegram-бота и собирает мобильные приложения.

> Блок работ: `blocks/BLOCK-28-autosetup.md` · Статус: ✅ 12.09.2026

---

## Сценарий 1. Локально за 5 минут (демо/разработка)

```bash
git clone https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git
cd Magazin_site_sklad_apk
./setup.sh
```

Мастер спросит только нужное (всё можно пропустить Enter'ом):
домен, токен бота от [@BotFather](https://t.me/BotFather), Telegram ID
админов (узнать: [@userinfobot](https://t.me/userinfobot)), пароль админки
(пусто — сгенерируется), оплату, режим бота. Дальше — установка
зависимостей, `.env`, предложение настроить бота — и сервер на `:8000`:

| Что | Адрес |
|---|---|
| Сайт / каталог | `http://localhost:8000/` · `/catalog` |
| Mini App | `http://localhost:8000/app` |
| Админка | `http://localhost:8000/admin` |
| Склад (PWA) | `http://localhost:8000/warehouse/` — логин `admin`, пароль из `.env` |
| Продавец | `http://localhost:8000/seller` |
| APK «Склад» / «Магазин» | `/download/android` · `/download/app` |

Полезные флаги: `--venv` (изолированное окружение), `--no-run`
(только установить), `--test` (прогон `run-tests.sh` перед стартом),
`--non-interactive` + `SETUP_*` (без вопросов, для скриптов).

Проверка в любой момент:

```bash
./setup.sh --check     # .env, секреты, boot сервера и health страниц
```

## Сценарий 2. Чистый VPS одной командой (production)

Требования: Ubuntu/Debian, root, DNS домена уже указывает на VPS.

```bash
git clone --depth 1 https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git
cd Magazin_site_sklad_apk
sudo -E ./setup.sh --vps --domain shop.ru \
  --bot-token 123456:ABC... --admin-ids 111222333 \
  --payment test --bot-mode webhook
# для HTTPS добавьте: LETSENCRYPT_EMAIL=admin@shop.ru
```

Что происходит (см. `deploy/bootstrap-vps.sh`):
1. Пакеты (git, python, nginx, certbot); на VPS с RAM < 2 ГБ — swap 2 ГБ.
2. Код в `/opt/magazin-shop`, пользователь `magazin`, venv, зависимости.
3. `.env` через мастер (интерактивно под sudo или из `SETUP_*`), `chmod 600`.
4. systemd-сервис `magazin-shop`, nginx, HTTPS через certbot (если задан email).
5. Таймеры: ежедневный бэкап, ротация, watchdog.
6. Health-check и итоговая сводка с адресами.

После установки — три команды из сводки:

```bash
./deploy/post-deploy-smoke.sh https://shop.ru          # дымовой тест
python3 /opt/magazin-shop/telegram-shop/scripts/setup_bot.py   # Telegram
/opt/magazin-shop/deploy/build-apps.sh --url https://shop.ru   # APK с адресом
```

Затем — ручная приёмка по `DEVELOPER-MANUAL-VALIDATION.md` (реальное
железо, оплаты, 1С — это автоматизировать нельзя).

## Сценарий 3. Обновление production

```bash
sudo ./setup.sh --update     # или: DEPLOY_DOMAIN=https://shop.ru ./deploy/update.sh
```

Скрипт сначала копирует `data/shop.db` в `backups/shop-<дата>.db`
(ротация — последние 7), затем обновляет код, зависимости,
перезапускает сервис, проверяет health и smoke.

---

## Настройка Telegram-магазина

`telegram-shop/scripts/setup_bot.py` — только стандартная библиотека,
работает до установки зависимостей:

```bash
python3 telegram-shop/scripts/setup_bot.py --dry-run      # план без сети
python3 telegram-shop/scripts/setup_bot.py --check-only   # проверить токен
python3 telegram-shop/scripts/setup_bot.py                # полная настройка
```

Делает: `getMe` → `setMyCommands` (7 реальных команд из `bot.py`) →
кнопка меню «🛍 Каталог» (WebApp на витрину) → `setWebhook`/`deleteWebhook`
по `BOT_MODE` → тестовое сообщение админам. Бот при старте повторяет
настройку сам — скрипт нужен для проверки **до** запуска сервера.

| BOT_MODE | Когда |
|---|---|
| `polling` (по умолчанию) | локально, без домена, разработка |
| `webhook` | production с https-доменом (мастер сам откатится на polling без https) |

## Мобильные приложения

```bash
./deploy/build-apps.sh --url https://shop.ru   # оба приложения
./deploy/build-apps.sh --sklad-only            # только «Склад»
./deploy/build-apps.sh --shop-only             # только «Магазин»
./deploy/build-apps.sh --skip-build            # только отчёт по готовым APK
```

Первая сборка скачивает JDK 17 + Android SDK в `~/.cache` (~500 МБ,
без sudo). Адрес сервера зашивается внутрь — на телефоне ничего вводить
не нужно. На выходе: таблица артефактов (размер, SHA-256), страницы
`/download/android` и `/download/app`, deep links и QR в терминале:

- Склад: `sklad://setup?url=https://shop.ru/warehouse/`
- Магазин: `shop://connect?url=https://shop.ru/`

Готовые APK также лежат в `telegram-shop/apk/` и собираются в CI.

## Все переменные автонастройки

| Переменная / флаг | Назначение |
|---|---|
| `SETUP_DOMAIN` / `--domain` | домен → `WEBAPP_URL`, `CORS_ORIGINS`, `TRUSTED_HOSTS` |
| `SETUP_BOT_TOKEN` / `--bot-token` | токен от @BotFather (пусто = бот выкл, сайт работает) |
| `SETUP_ADMIN_IDS` / `--admin-ids` | ID админов через запятую |
| `SETUP_ADMIN_PASSWORD` / `--admin-password` | пароль админки/склада (пусто = сгенерировать) |
| `SETUP_PAYMENT_PROVIDER` / `--payment` | `test` (по умолч.) `yookassa` `tbank` `cryptobot` `stars` |
| `SETUP_BOT_MODE` / `--bot-mode` | `polling` (по умолч.) `webhook` |
| `SETUP_WEBAPP_URL` | переопределить URL витрины (по умолч. `https://домен`) |
| `SETUP_YES=1` / `--non-interactive` | не задавать вопросов |
| `SETUP_FCM_CREDENTIALS_JSON` | Firebase service account JSON (вручную; пусто = FCM выкл) |
| `SETUP_FCM_DRY_RUN` | `1` (по умолч., dry-run) `0` — боевые push после staging |
| `DEPLOY_DOMAIN`, `DEPLOY_ROOT`, `DEPLOY_USER`, `LETSENCRYPT_EMAIL`, `DEPLOY_REPO` | параметры VPS-установки |
| `SETUP_SKIP_HTTPS=1` | пропустить certbot |
| `SETUP_MOBILE_URL` / `--url` | адрес сервера для сборки APK |

Правила безопасности: секреты выводятся только замаскированными
(кроме сгенерированного пароля — один раз); `.env` — `chmod 600`;
токены не попадают в git, логи CI и APK (проверяется `secret-scan.sh`
и `setup.sh --check`).

## Приёмка staging (авто-часть блока 17)

```bash
./deploy/staging-report.sh https://staging.example.com
WH_LOGIN=admin WH_PASSWORD=... ./deploy/staging-report.sh https://staging.example.com --out report.md
./deploy/backup-drill.sh --db telegram-shop/data/shop.db   # авто-прогон backup/restore (блок 18)
```

Отчёт собирает smoke, HTTPS, security-заголовки, версии API и локальные
ворота + печатает чек-лист ручного остатка. Ручное (железо, боевые оплаты
и 1С, скриншоты) — по `DEVELOPER-MANUAL-VALIDATION.md`.

## FAQ

**Токена пока нет — можно ставить?** Да. Бот отключится, всё остальное
(сайт, склад, админка, API) работает. Токен добавьте позже: мастер
(`--force`) или `./setup.sh --setup-bot`.

**Как сменить домен?** `SETUP_DOMAIN=новый ./deploy/setup-env.sh --force`,
перезапустить сервис, пересобрать APK новым `--url`.

**Что не автоматизируется?** Реальные устройства (ТСД, принтеры),
боевые оплаты, обмен с боевой 1С, staging-публикации в соцсетях,
Wildberries — см. блоки 11, 17, 18, 22 и `DEVELOPER-MANUAL-VALIDATION.md`.

**Docker?** `docker compose up -d --build`, затем `.env` — мастером:
`SETUP_ENV_FILE=telegram-shop/.env ./deploy/setup-env.sh`.

**Старый `install.sh`?** Работает как раньше (простая установка +
запуск). Для новых установок рекомендуется `./setup.sh`.
