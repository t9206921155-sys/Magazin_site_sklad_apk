#!/bin/bash
# Резервное копирование данных магазина.
# Запуск: ./scripts/backup.sh
# Cron: 0 3 * * * cd /path/telegram-shop && ./scripts/backup.sh >> /var/log/telegram-shop-backup.log 2>&1
#
# Делает два действия:
# 1) локальный tar.gz-архив папки data (+ .env, если есть)
# 2) отдельный снимок SQLite-базы и загрузку в S3/Yandex Object Storage
#    через настройки, сохранённые в складе (bucket shop-backups и т.п.)
set -e
cd "$(dirname "$0")/.."

TS=$(date +%Y%m%d-%H%M%S)
mkdir -p backups
tar czf "backups/backup-${TS}.tar.gz" data .env 2>/dev/null || tar czf "backups/backup-${TS}.tar.gz" data

echo "Локальный бэкап создан: backups/backup-${TS}.tar.gz"

# храним последние 14 локальных копий
ls -1t backups/backup-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "Старые локальные копии удалены (оставлено 14)."

if [ "${SKIP_CLOUD_BACKUP:-0}" = "1" ]; then
  echo "Загрузка SQLite-бэкапа в облако пропущена (SKIP_CLOUD_BACKUP=1)."
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "WARN: python3 не найден, выгрузка SQLite-бэкапа в облако пропущена." >&2
  exit 0
fi

echo "Пробуем отправить SQLite-бэкап в облако..."
if python3 scripts/backup_sqlite_to_s3.py; then
  echo "SQLite-бэкап успешно выгружен в облако."
else
  echo "WARN: локальный архив создан, но выгрузка SQLite-бэкапа в облако не удалась." >&2
fi
