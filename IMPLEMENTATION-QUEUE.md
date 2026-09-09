# Implementation queue — подготовка к полному тестированию

Этот файл фиксирует остаток работ. Статус меняется только после кода и теста.

## P0 — перед production

- [x] Runtime storage layer: полный DatabaseProvider-контракт (catalog/product/stock/batch), SQLiteProvider, фабрика, диагностика, allowlist+маскирование секретов, контрактные тесты (блок 13). Живые провайдеры Supabase/MySQL/S3/YD — staging-проверка в блоках 14/17.
- [~] Yandex Disk: REST-интеграция готова; staging-проверка token/upload/public URL ожидает ручных credentials.
- [x] MySQL/MariaDB: `scripts/migrate_sqlite_to_mysql.py` — dry-run, копирование, сверка COUNT+SHA256 по всем таблицам, read-only источник, `--drop-existing`; DDL под strict MySQL 8. Реальный `--apply` на боевом MySQL — staging (блок 17).
- [x] Backup/restore: `scripts/verify_restore.py` — восстановление во временную БД + сверка с живой (COUNT, опц. SHA256); тесты tests-block14 (32/32). Восстановление на чистом VPS — блок 18.
- [~] Production smoke: скрипт готов; запуск на staging/production ожидает URL.
- [x] Security/observability (блок 15): rate limit login/1С/API, TTL сессий склада, маскирование секретов в логах, метрики латентности/статусов, диск в readiness, watchdog + TG-алерты, last_error бэкапа. CSP — бэктлог (нужен вынос inline-JS).
- [~] Security: CORS, metrics token, rate limit и headers готовы; ручной аудит production ожидает окружение.

## P1 — marketplace catalog

- [x] Полное API-покрытие фильтров и сортировки (блок 09, 08.09.2026: единый `_apply_catalog_filters`, пагинация `page/per_page/total/pages`, валидация параметров).
- [x] UI seller filter, condition, photo, negotiable, price (Mini App — клиентские, SSR `/catalog` — форма фильтров; флаг `negotiable` добавлен в модель товара и кабинет продавца).
- [x] Тесты empty catalog, спецсимволов, invalid params и pagination (`tests-block09.py`, 47/47).
- [ ] Скриншоты staging для каждого фильтра (ручной пункт — нужен staging URL).

## P2 — Marketplace 2.0 (блок 16, 08.09.2026)

- [x] Seller verification (было: verification_status + админ-подтверждение).
- [x] Store subscriptions (подписки на витрины + лента новинок).
- [x] Seller plans and listing limits (было: планы, лимиты 429).
- [x] Reservation and price negotiation (бронь с TTL + offers/countered).
- [x] Complaints, moderation and blacklist (жалобы, очередь, бан/разбан).
- [x] Escrow state machine (held_balance + escrow_days, авто-релиз).
- [x] Seller analytics and promotion (просмотры витрины, «поднять» на 24ч/7д cooldown).

## P3 — real hardware

- [~] Android APK: складское «Склад» 1.0.6 готово (apk/aab, подписано, QR/deep-link). Покупательское приложение НЕ сделано — болванка в mobile/; ТЗ и план: `mobile/ANDROID-APP-TZ.md`, `blocks/BLOCK-25-mobile-buyer-app.md` (блок 25).
- [ ] HID/ТСД.
- [ ] Zebra/Eltron.
- [ ] IP printer.
- [ ] Offline mode on real Wi-Fi.

## Правила приёмки

1. Каждый пункт получает код, тест и запись в отчёте блока.
2. Для внешних сервисов обязательна staging-проверка без production secrets.
3. Для оборудования обязательны ручной результат и screenshot.
4. Нельзя переводить блок в ✅ только по наличию заглушки или документации.
5. После каждого завершённого этапа: `git status`, проверка mode change, commit и push.


## Handoff

Кодовая часть без credentials подготовлена. Для завершения ручных пунктов используйте `telegram-shop/.env.production.example`, `PRODUCTION-SETUP.md` и `DEVELOPER-MANUAL-VALIDATION.md`. Не переводить пункты `[~]` в `[x]` без реального результата и screenshot.
