# Implementation queue — подготовка к полному тестированию

Этот файл фиксирует остаток работ. Статус меняется только после кода и теста.

## P0 — перед production

- [ ] Runtime storage layer: перевести операции каталога/фото на единые provider-интерфейсы.
- [ ] Yandex Disk: проверить upload, public URL, overwrite и expired token на staging.
- [ ] MySQL/MariaDB: миграция SQLite, сверка данных и rollback.
- [ ] Backup/restore: автоматическая проверка восстановления на чистой БД.
- [ ] Production smoke: staging и production URL.
- [ ] Security: CORS, metrics token, rate limit, секреты в логах.

## P1 — marketplace catalog

- [ ] Полное API-покрытие фильтров и сортировки.
- [ ] UI seller filter, condition, photo, negotiable, price.
- [ ] Тесты empty catalog, спецсимволов, invalid params и pagination.
- [ ] Скриншоты staging для каждого фильтра.

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
