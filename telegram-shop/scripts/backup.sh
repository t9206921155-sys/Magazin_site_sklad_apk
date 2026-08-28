#!/bin/bash
# Резервное копирование данных магазина.
# Запуск: ./scripts/backup.sh  (или cron: 0 3 * * * cd /path/telegram-shop && ./scripts/backup.sh)
set -e
cd "$(dirname "$0")/.."

TS=$(date +%Y%m%d-%H%M%S)
mkdir -p backups
tar czf "backups/backup-${TS}.tar.gz" data .env 2>/dev/null || tar czf "backups/backup-${TS}.tar.gz" data

echo "Бэкап создан: backups/backup-${TS}.tar.gz"

# храним последние 14 копий
ls -1t backups/backup-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "Старые копии удалены (оставлено 14)."
