# Блок 15 — Production security и observability

**Статус:** ✅ выполнено (08.09.2026)

## Цель
Сделать production-эксплуатацию безопасной и диагностируемой.

## Задачи
- [x] аудит CORS, trusted hosts, cookies и security headers:
      CORS — `CORS_ORIGINS` из env (по умолчанию `*`, credentials не включены);
      `TRUSTED_HOSTS` (env, пусто = проверка off) подключает TrustedHostMiddleware;
      cookies не используются (токены в заголовках — CSRF-риск минимален);
      security headers: nosniff, X-Frame-Options, Referrer-Policy, Permissions-Policy,
      HSTS при https. CSP не ставился: фронт использует inline-скрипты (ломал бы UI),
      отмечено как бэктлог вместе с выносом JS.
- [x] ротация токенов и проверка срока действия секретов:
      1С-токен перевыпускается в админке (`reset_1c_token`); складской токен = HMAC
      от login+pass_hash — смена пароля автоматически инвалидирует все токены;
      сессии быстрого входа получили TTL `WH_SESSION_TTL_DAYS` (дней неактивности,
      по умолчанию 30): просроченная сессия отклоняется и удаляется, старьё
      подчищается при каждом входе.
- [x] структурированные логи без токенов и паролей: `SecretMaskingFilter`
      на логгерах shop/shop.api — маскирует `token=`, `password=`, `secret=`,
      `api_key=`, `access_key=` в любом сообщении; обычный текст не искажается.
- [x] метрики ошибок API, времени ответа и доступности storage:
      `/metrics` отдаёт requests, errors, error_rate, uptime, латентность
      (avg/p95/max, бакеты), распределение статус-кодов и `last_backup_error`.
      Только счётчики — секретов нет; при заданном `METRICS_TOKEN` — по токену.
- [x] уведомление при падении сервера, заполнении диска и неудачном backup:
      `scripts/server_watchdog.sh` (health-check + df, Telegram-алерт через
      BOT_TOKEN/ADMIN_IDS, анти-дребезг 1ч для диска, уведомление о восстановлении)
      + `deploy/magazin-watchdog.service` (systemd, Restart=always);
      неудачный backup пишет `last_error/last_error_at` в cloud_state → виден в
      `/api/warehouse/cloud/status` и `/metrics`; успешный — очищает.
- [x] rate limit для login, 1С и публичных endpoint: окно 60с по IP —
      `AUTH_RATE_LIMIT` (login, 20/мин), `RATE_LIMIT_1C` (120/мин),
      `RATE_LIMIT_API` (600/мин); превышение → 429 с понятным текстом.

## Приёмка
- [x] секреты отсутствуют в логах — фильтр-тест на 4 вида секретов + негативный кейс
- [x] health/metrics не раскрывают чувствительные данные — тесты ищут admin123/токены
- [x] security smoke и regression проходят — tests-block15 40/40, вся регрессия зелёная

## Отчёт (сессия 08.09.2026) — блок закрыт

### Что сделано
- `config.py`: `TRUSTED_HOSTS`, `RATE_LIMIT_1C`, `RATE_LIMIT_API`,
  `WH_SESSION_TTL_DAYS`, `DISK_FREE_MIN_MB` (всё через env с безопасными дефолтами).
- `api.py`:
  - rate limit обобщён (`_rate_check`, окно 60с, ключ = префикс+IP, ограничение памяти);
  - TrustedHostMiddleware по конфигу;
  - `request_observability` копит латентность (бакеты) и статус-коды;
  - `/metrics` расширен (безопасные агрегаты + last_backup_error);
  - `/health/ready` проверяет свободное место (`disk_free_mb`, `disk`);
  - `SecretMaskingFilter`/`mask_secrets` для логов;
  - backup: `last_error` в cloud_state при неудаче, очистка при успехе.
- `store.py`: TTL сессий быстрого входа (`_purge_expired_sessions` + проверка возраста).
- `scripts/server_watchdog.sh` + `deploy/magazin-watchdog.service`.
- Найден и исправлен по ходу: `/api/warehouse/cloud/status` не показывал
  `last_error` (собирал ответ литералом без новых ключей).

### Тесты (`tests-block15.py` — 40/40)
headers (6) · CORS (2) · metrics без секретов (8) · readiness+диск (5) ·
маскирование логов (5) · backup last_error (4) · TTL сессий (5) · watchdog (3) ·
rate limit 1С+login (4). Флуд-тесты стоят в конце файла — после прогона IP в
карантине ~60с, поэтому блок 15 запускается ПОСЛЕДНИМ в регрессии
(порядок зафиксирован в ROADMAP).
Регрессия: labels 20/20, hid 8/8, stage5 23/23, block06 33/33, block09 47/47,
block13 33/33, block14 32/32, contracts 32/32, pytest 16/16.

### Вне блока (ручное/staging)
- CSP (нужен вынос inline-скриптов фронтов) — бэктлог.
- Внешний алертинг (Zabbix/Uptime-Kuma) и реальный прогон watchdog с BOT_TOKEN — блок 17.
