# Implementation queue — подготовка к полному тестированию

Этот файл фиксирует остаток работ. Статус меняется только после кода и теста.

## P0 — перед production

- [x] Runtime storage layer: полный DatabaseProvider-контракт (catalog/product/stock/batch), SQLiteProvider, фабрика, диагностика, allowlist+маскирование секретов, контрактные тесты (блок 13). Живые провайдеры Supabase/MySQL/S3/YD — staging-проверка в блоках 14/17.
- [~] Yandex Disk: REST-интеграция готова; staging-проверка token/upload/public URL ожидает ручных credentials.
- [ ] MySQL/MariaDB: миграция SQLite, сверка данных и rollback.
- [ ] Backup/restore: автоматическая проверка восстановления на чистой БД.
- [~] Production smoke: скрипт готов; запуск на staging/production ожидает URL.
- [~] Security: CORS, metrics token, rate limit и headers готовы; ручной аудит production ожидает окружение.

## P1 — marketplace catalog

- [x] Полное API-покрытие фильтров и сортировки (блок 09, 08.09.2026: единый `_apply_catalog_filters`, пагинация `page/per_page/total/pages`, валидация параметров).
- [x] UI seller filter, condition, photo, negotiable, price (Mini App — клиентские, SSR `/catalog` — форма фильтров; флаг `negotiable` добавлен в модель товара и кабинет продавца).
- [x] Тесты empty catalog, спецсимволов, invalid params и pagination (`tests-block09.py`, 47/47).
- [ ] Скриншоты staging для каждого фильтра (ручной пункт — нужен staging URL).

## P2 — Marketplace 2.0

- [ ] Seller verification.
- [ ] Store subscriptions.
- [ ] Seller plans and listing limits.
- [ ] Reservation and price negotiation.
- [ ] Complaints, moderation and blacklist.
- [ ] Escrow state machine.
- [ ] Seller analytics and promotion.

## P3 — real hardware

- [ ] Android APK.
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
