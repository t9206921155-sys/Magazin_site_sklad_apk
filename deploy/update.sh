#!/usr/bin/env bash
# ============================================================
#  Telegram Shop — безопасное обновление на VPS
#
#  1) бэкапит SQLite-базу (data/shop.db) с меткой времени;
#  2) делегирует обновление deploy/auto-deploy-vps.sh
#     (git fetch/reset, зависимости, systemd restart, health);
#  3) при DEPLOY_DOMAIN прогоняет post-deploy smoke.
#
#  Запуск:
#    ./deploy/update.sh
#    ./deploy/update.sh --dry-run
#    DEPLOY_ROOT=/opt/magazin-shop DEPLOY_BRANCH=main \
#      DEPLOY_SERVICE=magazin-shop DEPLOY_DOMAIN=https://shop.ru \
#      ./deploy/update.sh
#
#  Бэкапы: $DEPLOY_ROOT/backups/shop-YYYYmmdd-HHMMSS.db (+ ротация: последние 7).
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_ROOT_DIR="${DEPLOY_ROOT:-$ROOT}"
DRY_RUN=0

usage(){ sed -n '2,/^# ===/p' "$0" | sed 's/^# \{0,1\}//'; }
log(){ printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✅\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  ⚠️\033[0m %s\n' "$*"; }

for a in "$@"; do case "$a" in
  --dry-run) DRY_RUN=1 ;;
  --help|-h) usage; exit 0 ;;
  *) echo "Неизвестный аргумент: $a" >&2; exit 1 ;;
esac; done

DB="$DEPLOY_ROOT_DIR/telegram-shop/data/shop.db"
BACKUP_DIR="$DEPLOY_ROOT_DIR/backups"

if [ "$DRY_RUN" = 1 ]; then
  log "DRY-RUN: план обновления"
  echo "  1. бэкап $DB -> $BACKUP_DIR/shop-<дата>.db"
  echo "  2. deploy/auto-deploy-vps.sh (ветка ${DEPLOY_BRANCH:-main}, сервис ${DEPLOY_SERVICE:-magazin-shop})"
  [ -n "${DEPLOY_DOMAIN:-}" ] && echo "  3. post-deploy smoke: $DEPLOY_DOMAIN"
  exit 0
fi

if [ -f "$DB" ]; then
  mkdir -p "$BACKUP_DIR"
  SNAP="$BACKUP_DIR/shop-$(date +%Y%m%d-%H%M%S).db"
  cp "$DB" "$SNAP" && ok "бэкап базы: $SNAP ($(du -h "$SNAP" | cut -f1))"
  # ротация: держать последние 7 снапшотов
  ls -1t "$BACKUP_DIR"/shop-*.db 2>/dev/null | tail -n +8 | xargs -r rm -f
else
  warn "базы $DB нет — бэкап пропущен (первая установка?)"
fi

bash "$ROOT/deploy/auto-deploy-vps.sh"
ok "обновление завершено"
