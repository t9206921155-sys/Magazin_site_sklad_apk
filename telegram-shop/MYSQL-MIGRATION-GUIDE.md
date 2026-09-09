# 🗄 Миграция SQLite → MySQL/MariaDB и проверка бэкапов (блок 14)

> Прочитай до конца один раз — потом это будет 15 минут по чек-листу.
> Все команды выполняются на VPS из корня репозитория (`/opt/Magazin_site_sklad_apk`).

---

## 0. Безопасность (почему это не страшно)

- Исходная SQLite открывается **только в read-only** — миграция физически не может
  её повредить.
- Всё по умолчанию **dry-run**: без `--apply` ни один байт в MySQL не пишется.
- Откат в любой момент: рабочей базой остаётся SQLite (`db_mode=vps`). MySQL —
  отдельная база, сайт на неё не смотрит, пока вы явно не переключите режим в
  настройках склада.
- Каждая таблица после копирования сверяется: **количество записей + SHA256 строк**.

---

## 1. Бэкап (всегда первый шаг)

```bash
# атомарный снимок живой базы + загрузка в S3-bucket бэкапов
python3 telegram-shop/scripts/backup_sqlite_to_s3.py

# или через API (токен склада):
curl -X POST https://ВАШ-СЕРВЕР/api/warehouse/cloud/backup -H "X-WH-Token: $TOK"

# локальный атомарный снимок руками (без облака):
python3 -c "import sys; sys.path.insert(0,'telegram-shop'); from store import store; store.export_sqlite_backup('backups/manual-$(date +%F).db')"
```

Бэкап идёт в отдельный bucket (`backup_bucket`, по умолчанию `shop-backups`),
префикс `backup_prefix` (по умолчанию `sqlite`). Ретеншн:

```bash
python3 telegram-shop/scripts/backup_retention.py --keep 30          # отчёт
python3 telegram-shop/scripts/backup_retention.py --keep 30 --apply  # удалить старые
```

## 2. Проверка восстановления (до любой миграции)

```bash
# integrity + восстановление во временную БД + сверка с живой по всем таблицам
python3 telegram-shop/scripts/verify_restore.py backups/shop-XXXX.db \
  --expect-live telegram-shop/data/shop.db --checksum
```

Ожидаемый финал: `Восстановление валидно ✔`. Если `РАСХОЖДЕНИЕ` — бэкап битый,
миграцию не начинать, сделать свежий бэкап.

Точечная проверка восстановления «как в бою» (замена рабочей базы на копию):

```bash
python3 telegram-shop/scripts/restore_sqlite.py backups/shop-XXXX.db \
  --target /tmp/shop-restored.db --apply   # во временную — рабочая база не тронута
```

## 3. Миграция SQLite → MySQL/MariaDB

### 3.1 Dry-run (план без записи)

```bash
python3 telegram-shop/scripts/migrate_sqlite_to_mysql.py
# возьмёт mysql_* из настроек склада, покажет план: таблицы и количества записей
```

### 3.2 Применение

```bash
python3 telegram-shop/scripts/migrate_sqlite_to_mysql.py \
  --host mysql.host.ru --port 3306 --user shop --password '***' --database shop \
  --apply --drop-existing
```

Скрипт сам создаёт таблицы (SQLite DDL переводится в MySQL: `INTEGER PRIMARY KEY
AUTOINCREMENT` → `BIGINT AUTO_INCREMENT PRIMARY KEY` и т.п.), копирует данные
батчами по 200 и печатает таблицу сверки. Успех = `OK` у всех таблиц и строка
«количества и контрольные суммы совпадают».

Если что-то пошло не так: `--drop-existing` пересоздаёт таблицы на цели, источник
при этом не затрагивается никогда.

### 3.3 Переключение и откат

- **Включить MySQL**: админка склада → Настройки → База → `MYSQL`, указать хост/базу →
  сохранить → «Проверить облако» (ping должен быть ok).
- **Откат** (в любой момент): вернуть режим `VPS` в той же настройке. Сайт
  продолжает работать на SQLite, данные в MySQL никуда не деваются.

## 4. Инструкция для phpMyAdmin (если нет SSH-доступа к MySQL)

1. Сгенерировать SQL-дамп из SQLite:
   ```bash
   python3 telegram-shop/scripts/export_sqlite_sql.py telegram-shop/data/shop.db -o /tmp/shop-export.sql
   ```
2. Открыть дамп в редакторе и **просмотреть перед импортом** (это черновой экспорт):
   - файл должен начинаться с `SET NAMES utf8mb4;`
   - удалить строки с `sqlite_sequence`, если встретятся;
   - проверить, что `CREATE TABLE` выглядят разумно (типы INTEGER/TEXT совместимы).
3. В phpMyAdmin: выбрать базу → вкладка **Импорт** → файл `/tmp/shop-export.sql`
   → формат SQL → кодировка **utf-8** → Вперёд.
4. После импорта: структура → сверить число таблиц и записей с dry-run-планом
   из п. 3.1 (`migrate_sqlite_to_mysql.py` печатает точные количества).
5. Создать пользователя для склада (только DML на эту базу) и указать его в
   настройках `cloud.mysql_*`.

> Если таблицы уже созданы скриптом миграции — импорт дампа в phpMyAdmin
> поверх задвоит данные. Используйте что-то одно: скрипт **или** phpMyAdmin.

## 5. Чек-лист приёмки блока

- [ ] `verify_restore.py --expect-live --checksum` → «Восстановление валидно ✔»
- [ ] `migrate_sqlite_to_mysql.py` (dry-run) → план без ошибок
- [ ] `--apply` → все таблицы `OK`, «количества и контрольные суммы совпадают»
- [ ] После переключения `db_mode=mysql`: сайт открывается, товары на месте,
      заказ создаётся, склад показывает остатки
- [ ] Откат на `db_mode=vps` работает, данные на месте
- [ ] Исходный `shop.db`: `PRAGMA integrity_check` = ok до и после всего
