# Блок 14 — Backup, restore и MySQL/MariaDB

**Статус:** ✅ выполнено (08.09.2026)

## Цель
Подтвердить, что данные можно восстановить, а MySQL/MariaDB на VPS подключается без потери данных.

## Задачи
- [x] атомарный SQLite backup через backup API
      (`store.export_sqlite_backup` — sqlite3 backup API; `POST /api/warehouse/cloud/backup`;
      уже существовал — покрыт тестами)
- [x] upload backup в отдельный bucket (`backup_bucket`/`backup_prefix`, S3-совместимое;
      скрипты `backup_sqlite_to_s3.py`, `backup.sh`, ретеншн `backup_retention.py` — dry-run by default)
- [x] restore в временную БД — `scripts/verify_restore.py` восстанавливает бэкап
      во временную базу (рабочая не трогается); точечная замена цели — `restore_sqlite.py`
      (integrity + SHA256 + dry-run по умолчанию + `--backup-current`)
- [x] export/import SQLite → MySQL/MariaDB — `scripts/migrate_sqlite_to_mysql.py`:
      автодискавер всех таблиц из sqlite_master, DDL-трансляция под строгий MySQL 8,
      копирование батчами, сверка каждой таблицы; черновой SQL-дамп для phpMyAdmin —
      `scripts/export_sqlite_sql.py`
- [x] проверка товаров, заказов, складов, пользователей и настроек —
      сверка количеств записей и SHA256 строк по ВСЕМ таблицам (в тестах — явно
      products/orders/wh_stock/users+wh_users/settings)
- [x] rollback и dry-run миграции: dry-run по умолчанию; источник read-only
      (`file:...?mode=ro`) — исходная БД повредить невозможно; откат = вернуть
      `db_mode=vps`; пересоздание цели — `--drop-existing`
- [x] инструкция для phpMyAdmin — `telegram-shop/MYSQL-MIGRATION-GUIDE.md`

## Приёмка
- [x] восстановление проходит на чистой среде — verify_restore восстанавливает
      бэкап в чистую временную БД и проверяет ключевые таблицы
      (tests-block14: валидный → exit 0, подделанный → exit 1)
- [x] контрольные суммы и количество записей совпадают —
      сверка SHA256 канонической сериализации строк + COUNT по каждой таблице
- [x] ошибки миграции не повреждают исходную БД — read-only источник
      (тест: sha256 копии источника до/после миграции идентичны; integrity ok)

## Отчёт (сессия 08.09.2026) — блок закрыт

### Что сделано
- **`scripts/migrate_sqlite_to_mysql.py`** (новый): dry-run по умолчанию, `--apply`
  с копированием и полной сверкой (COUNT + SHA256 по каждой из 36 таблиц),
  `--drop-existing` для перезапуска. DDL-трансляция: `INTEGER PRIMARY KEY AUTOINCREMENT`
  → `BIGINT AUTO_INCREMENT PRIMARY KEY`; `TEXT PRIMARY KEY/UNIQUE` → `VARCHAR(191) …`
  (TEXT-ключи невалидны в strict MySQL 8); литеральные `TEXT DEFAULT '…'` убираются —
  приложение всегда вставляет все колонки явно, миграция переносит полные строки.
  Креды берутся из `cloud.mysql_*` настроек склада или CLI.
- **`scripts/verify_restore.py`** (новый): integrity_check → восстановление во
  временную БД → сверка количеств по всем таблицам с живой базой (`--expect-live`),
  опционально контрольные суммы строк (`--checksum`); понятный отчёт, exit-коды.
- **`MYSQL-MIGRATION-GUIDE.md`** (новый): бэкап → проверка восстановления → миграция
  dry-run/apply → переключение/откат → инструкция phpMyAdmin → чек-лист приёмки.
- Логика миграции инъекция-тестируема (`migrate_apply(src, target, …)`) —
  проверена на фейковом таргете без реального MySQL.

### Тесты (`tests-block14.py` — 32/32)
- Backup API без S3 → ok=False «Не заданы endpoint/ключи S3» (без падений);
- атомарный снимок: integrity ok, количества всех таблиц = живой базе;
- verify_restore: валидный бэкап → 0; из бэкапа удалён товар → РАСХОЖДЕНИЕ, exit 1;
- restore dry-run цель не трогает;
- DDL-трансляция: 4 кейса strict MySQL 8;
- dry-run миграции: план 36 таблиц без записи;
- фейковый MySQL: полная копия сходится, потеря строки детектируется (exit 1);
- sha256 источника до/после миграции идентичны, integrity_check живой базы ok.
- Регрессия: block13 33/33, contracts 32/32, block09 47/47, stage5 23/23,
  block06 33/33, labels 20/20, hid 8/8, pytest 16/16; страницы — 200.

### Вне блока (staging, ручное — блок 17/18)
- Реальный прогон `--apply` на боевом MySQL/MariaDB и переключение `db_mode=mysql`.
- Восстановление S3-бэкапа на чистом VPS (блок 18).
