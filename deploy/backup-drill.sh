#!/usr/bin/env bash
# ============================================================
#  Telegram Shop — авто-прогон backup/restore (блок 18, часть авто)
#
#  Безопасно для живой базы (только чтение):
#    1) онлайн-снимок SQLite через backup API (не cp живого файла);
#    2) gzip + SHA-256 manifest;
#    3) восстановление во временную БД + сверка с живой
#       (scripts/verify_restore.py --expect-live);
#    4) markdown-отчёт.
#
#  Запуск:
#    ./deploy/backup-drill.sh
#    ./deploy/backup-drill.sh --db /opt/magazin-shop/telegram-shop/data/shop.db
#    ./deploy/backup-drill.sh --out-dir /tmp/drill --checksum --keep
#    ./deploy/backup-drill.sh --dry-run
#
#  Переменные: MAGAZIN_DB (путь к живой БД), TELEGRAM_SHOP_DIR.
#  Живая база НЕ изменяется. Ручной остаток блока 18 (systemd-таймеры,
#  внешнее хранилище, restore на чистом VPS) — см. blocks/BLOCK-18*.
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${TELEGRAM_SHOP_DIR:-$ROOT/telegram-shop}"

DB="${MAGAZIN_DB:-$APP_DIR/data/shop.db}"
OUT_DIR=""; DO_CHECKSUM=0; DRY_RUN=0; KEEP=0

usage(){ sed -n '2,/^# ===/p' "$0" | sed 's/^# \{0,1\}//'; }
log(){ printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✅\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m  ❌\033[0m %s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do case "$1" in
  --db) DB="$2"; shift 2 ;;
  --out-dir) OUT_DIR="$2"; shift 2 ;;
  --checksum) DO_CHECKSUM=1; shift ;;
  --keep) KEEP=1; shift ;;
  --dry-run) DRY_RUN=1; shift ;;
  --help|-h) usage; exit 0 ;;
  *) die "Неизвестный аргумент: $1 (--help для справки)" ;;
esac; done

[ -z "$OUT_DIR" ] && OUT_DIR="$ROOT/drill-$(date +%Y%m%d-%H%M%S)"

if [ "$DRY_RUN" = 1 ]; then
  log "DRY-RUN: план backup-drill"
  echo "  БД:        $DB"
  echo "  Каталог:   $OUT_DIR/"
  echo "  1. онлайн-снимок (sqlite backup API) -> snapshot.db"
  echo "  2. gzip + SHA-256 -> snapshot.db.gz + MANIFEST.sha256"
  echo "  3. verify_restore.py --expect-live живой_БД (восстановление во временную)"
  echo "  4. REPORT.md"
  exit 0
fi

[ -f "$DB" ] || die "нет базы $DB (укажите --db или MAGAZIN_DB)"
command -v python3 >/dev/null || die "нужен python3"
mkdir -p "$OUT_DIR"
SNAP="$OUT_DIR/snapshot.db"

# 1. онлайн-снимок (консистентен даже при записи в живую базу)
log "Снимок $DB -> $SNAP"
python3 - "$DB" "$SNAP" <<'PY' || exit 1
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
print(f"snapshot ok: {sys.argv[2]}")
PY
[ -f "$SNAP" ] || die "снимок не создан"
ok "снимок $(du -h "$SNAP" | cut -f1)"

# 2. gzip + manifest
log "Архив + manifest"
gzip -kf "$SNAP"
( cd "$OUT_DIR" && sha256sum snapshot.db snapshot.db.gz > MANIFEST.sha256 )
ok "MANIFEST.sha256"

# 3. восстановление во временную + сверка (живая база не трогается)
log "Проверка восстановления (verify_restore.py)"
VERIFY_ARGS=("$SNAP" --expect-live "$DB")
[ "$DO_CHECKSUM" = 1 ] && VERIFY_ARGS+=(--checksum)
set +e
VERIFY_OUT="$(python3 "$APP_DIR/scripts/verify_restore.py" "${VERIFY_ARGS[@]}" 2>&1)"
VERIFY_CODE=$?
set -e
echo "$VERIFY_OUT" | tail -5
[ "$VERIFY_CODE" = 0 ] && ok "сверка с живой базой пройдена" || die "сверка НЕ пройдена (см. выше)"

# 4. отчёт
REPORT="$OUT_DIR/REPORT.md"
{
  echo "# Backup drill — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "- Живая БД: \`$DB\` (только чтение, не изменялась)"
  echo "- Снимок: \`snapshot.db\` ($(du -h "$SNAP" | cut -f1)), архив: \`snapshot.db.gz\` ($(du -h "$SNAP.gz" | cut -f1))"
  echo "- SHA-256: \`$(cut -d' ' -f1 "$OUT_DIR/MANIFEST.sha256" | head -1)\`… (полные — в MANIFEST.sha256)"
  echo "- Сверка: ✅ пройдена $([ "$DO_CHECKSUM" = 1 ] && echo "(COUNT + SHA256)" || echo "(COUNT)")"
  echo ""
  echo "```"
  echo "$VERIFY_OUT" | tail -15
  echo "```"
} > "$REPORT"
ok "отчёт: $REPORT"
[ "$KEEP" = 0 ] && rm -f "$SNAP" "$SNAP.gz" && echo "  (снимки удалены, оставлены MANIFEST.sha256 + REPORT.md; --keep сохраняет всё)"
log "Готово 🎉"
