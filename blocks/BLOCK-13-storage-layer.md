# Блок 13 — Единый storage layer

**Статус:** ✅ выполнено (08.09.2026)

## Цель
Унифицировать подключение SQLite, Supabase, MySQL/MariaDB, S3 и Yandex Disk через явные provider-интерфейсы.

## Задачи
- [x] `DatabaseProvider`: ping, catalog, product, stock, transaction-батч (`apply_batch`)
- [x] `PhotoStorage`: ping, upload, delete, public_url
- [x] Привести S3 и Yandex Disk к единому интерфейсу
- [x] Убрать разрозненные проверки режимов из UI (режимная логика склада централизована
      в `currentDbMode()/isDirectMode()`; бизнес-логика провайдеров — за контрактами)
- [x] Маскирование секретов и валидация конфигурации (allowlist полей + динамическая маскировка)
- [x] Контрактные тесты каждого провайдера (`tests-storage-contracts.py`, `tests-block13.py`)

## Приёмка
- [x] смена провайдера не требует изменения бизнес-логики — все режимы (vps/SQLite,
      supabase_proxy, supabase_direct, mysql) реализуют один `DatabaseProvider`;
      фабрика `database_provider_from_cloud(cloud, store)` возвращает провайдера по конфигу
- [x] недоступный provider даёт понятную ошибку — `{"ok": false, "error": "..."}` без
      исключений (в т.ч. сетевые сбои Yandex Disk больше не роняют вызовы)
- [x] service-role и OAuth secrets не уходят клиенту — маскировка в GET + allowlist в PUT

## Отчёт (текущий этап)

- Добавлены `DatabaseProvider` и `PhotoStorage` contracts.
- Добавлена общая фабрика `database_provider_from_cloud`.
- S3 и Yandex Disk поддерживают ping, upload, public URL и delete.
- Добавлены `/api/warehouse/cloud/providers` и `/api/warehouse/cloud/config-check`.
- Диагностика корректно показывает выбранный photo provider.
- Добавлены безопасные contract tests без credentials.
- Ручные проверки реальных Supabase, MySQL, S3 и Yandex Disk отложены до staging.

## Отчёт финальный (сессия 08.09.2026) — блок закрыт

### Контракт DatabaseProvider дополнен до плана блока
- `catalog()` — чтение каталога; `upsert_product(product)` — один товар;
  `upsert_stock(items)` — остатки/цены по кодам; `apply_batch(ops)` — батч
  (транзакционная семантика где возможно, best-effort с отчётом для REST).
- Общая реализация — `DatabaseProviderMixin` поверх push/pull; провайдер может
  переопределить метод нативным (MySQL делает UPDATE по коду без перезаливки каталога).
- Новый `SQLiteProvider` — локальная база режима vps как полноправный провайдер
  (нужен для «смены провайдера без изменения бизнес-логики» и офлайн-контрактных тестов).
- Фабрика: `database_provider_from_cloud(cloud, store=None)` — vps+store → SQLiteProvider.

### Безопасность (найдено и исправлено)
1. **Утечка OAuth-токена Яндекс Диска**: `GET /api/warehouse/settings` маскировал
   `key/public_key/s3_secret_key/mysql_password`, но возвращал `yandex_disk_token`
   в открытом виде любому складскому пользователю (включая роль worker). Исправлено.
2. **Неизвестные поля cloud-конфигурации проходили насквозь**: PUT мерджил произвольные
   поля, secret-подобное поле с неизвестным именем навсегда оседало в настройках и
   возвращалось клиенту без маскировки. Теперь: allowlist `CLOUD_FIELDS` в PUT
   (неизвестное — отбрасывается, настройки самовосстанавливаются) + динамическая
   маскировка любых secret-подобных полей (`token/secret/password/*key`) в GET.
3. **Сетевые исключения Yandex Disk не перехватывались** — сбой сети ронял
   `delete_photo`/`ping` необработанным исключением. Теперь понятная ошибка
   `Яндекс Диск недоступен: …` со статусом 503.

### Тесты
- `tests-storage-contracts.py` (офлайн, без сети и секретов): **32/32** — контракты
  классов, единый сценарий catalog→product→stock→batch на SQLiteProvider, понятные
  ошибки недоступных провайдеров, безопасность `provider_status`, фабрика режимов.
- `tests-block13.py` (живой сервер): **33/33** — маскирование всех секретов в GET,
  «•••» не затирает секреты при сохранении, allowlist отбрасывает неизвестные поля,
  config-check честно перечисляет missing без сети, providers/direct/config,
  cloud/test с понятными ошибками, восстановление настроек после теста.
- Регрессия: block09 47/47, stage5 23/23, block06 33/33, labels 20/20, hid 8/8,
  pytest 16/16; страницы /, /catalog, /shop, /app, /warehouse/, /sitemap.xml — 200.

### Вне блока (staging, ручное)
- Живые проверки Supabase/MySQL/S3/Yandex Disk с реальными credentials — блоки 14/17.
- Полный runtime-переход склада на провайдеров — после staging-проверки (блок 14/17).
