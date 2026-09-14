#!/usr/bin/env bash
# ============================================================
#  Telegram Shop — авто-отчёт приёмки staging/production (блок 17, часть авто)
#
#  Одной командой собирает всё автоматизируемое из
#  DEVELOPER-MANUAL-VALIDATION.md и пишет markdown-отчёт:
#    1) post-deploy smoke (с авторизацией, если заданы WH_LOGIN/WH_PASSWORD);
#    2) HTTPS-preflight (для https-URL);
#    3) security-заголовки (CSP строгий на витрине, Report-Only внутри);
#    4) версии API (Android-склад, покупательское приложение);
#    5) локальные ворота: check-env-keys, secret-scan, env-preflight;
#    6) чек-лист ручного остатка (скриншоты, железо, 1С, оплаты).
#
#  Запуск (с сервера или с локальной машины — нужен лишь curl):
#    ./deploy/staging-report.sh https://staging.example.com
#    ./deploy/staging-report.sh https://staging.example.com --out report.md
#    WH_LOGIN=admin WH_PASSWORD=... ./deploy/staging-report.sh https://...
#    ./deploy/staging-report.sh --dry-run
#
#  Exit code: 0 — все авто-проверки зелёные; 1 — есть FAIL.
#  Ручные пункты в отчёте помечены [РУЧНОЕ] — их закрывает владелец
#  по DEVELOPER-MANUAL-VALIDATION.md со скриншотами.
# ============================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${TELEGRAM_SHOP_DIR:-$ROOT/telegram-shop}"

URL=""; OUT=""; DRY_RUN=0
usage(){ sed -n '2,/^# ===/p' "$0" | sed 's/^# \{0,1\}//'; }
die(){ echo "❌ $*" >&2; exit 2; }

while [ "$#" -gt 0 ]; do case "$1" in
  --out) OUT="$2"; shift 2 ;;
  --dry-run) DRY_RUN=1; shift ;;
  --help|-h) usage; exit 0 ;;
  -*) die "Неизвестный аргумент: $1 (--help для справки)" ;;
  *) URL="$1"; shift ;;
esac; done

if [ "$DRY_RUN" = 1 ]; then
  echo "DRY-RUN: staging-report соберёт smoke + https + headers + versions + local gates"
  echo "и запишет markdown-отчёт + чек-лист [РУЧНОЕ]. URL: ${URL:-не задан}"
  exit 0
fi

[ -n "$URL" ] || die "нужен URL: ./deploy/staging-report.sh https://staging.example.com"
URL="${URL%/}"
[ -z "$OUT" ] && OUT="$ROOT/staging-report-$(date +%Y%m%d-%H%M%S).md"
command -v curl >/dev/null || die "нужен curl"

PASS=0; FAIL=0; SKIP=0; DETAILS=""
rec(){ # rec <PASS|FAIL|SKIP> <название> [деталь]
  case "$1" in PASS) PASS=$((PASS+1));; FAIL) FAIL=$((FAIL+1));; *) SKIP=$((SKIP+1));; esac
  DETAILS="$DETAILS
- [$1] $2${3:+ — $3}"
  printf '[%s] %s\n' "$1" "$2"
}

# ---------- 1. smoke ----------
if SMOKE_OUT="$(bash "$ROOT/deploy/post-deploy-smoke.sh" "$URL" 2>&1)"; then
  rec PASS "post-deploy smoke" "$(echo "$SMOKE_OUT" | grep -c '^OK') проверок OK"
else
  rec FAIL "post-deploy smoke" "$(echo "$SMOKE_OUT" | grep '^FAIL' | head -3 | tr '\n' ';')"
fi

# ---------- 2. https ----------
case "$URL" in https://*)
  if HTTPS_OUT="$(bash "$ROOT/deploy/https-preflight.sh" "$URL" 2>&1)"; then
    rec PASS "HTTPS preflight"
  else
    rec FAIL "HTTPS preflight" "$HTTPS_OUT"
  fi ;;
  *) rec SKIP "HTTPS preflight" "URL не https" ;;
esac

# ---------- 3. security headers ----------
STRICT_OK=1; RO_OK=1
for p in / /catalog; do
  csp="$(curl -ksSI --max-time 10 "$URL$p" | grep -i '^content-security-policy:' | head -1 || true)"
  [ -n "$csp" ] || STRICT_OK=0
done
[ "$STRICT_OK" = 1 ] && rec PASS "CSP строгий на витрине (/, /catalog)" || rec FAIL "CSP строгий на витрине" "нет заголовка"
for p in /app /warehouse/ /admin/ /crm/ /shop; do
  ro="$(curl -ksSI --max-time 10 "$URL$p" | grep -i '^content-security-policy-report-only:' | head -1 || true)"
  [ -n "$ro" ] || RO_OK=0
done
[ "$RO_OK" = 1 ] && rec PASS "CSP Report-Only на внутренних (/app /warehouse /admin /crm /shop)" || rec FAIL "CSP Report-Only" "нет заголовка"

# ---------- 4. версии API ----------
ANDR_VER="$(curl -ksS --max-time 10 "$URL/api/releases/android" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("latest_apk") or d.get("latest") or {}).get("version","?"))' 2>/dev/null || echo "?")"
APP_VER="$(curl -ksS --max-time 10 "$URL/api/app/version" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version","?"))' 2>/dev/null || echo "?")"
[ "$ANDR_VER" != "?" ] && rec PASS "API версий" "Склад $ANDR_VER · Магазин $APP_VER" || rec FAIL "API версий" "не отвечает"

# ---------- 5. локальные ворота ----------
if [ -d "$ROOT/.git" ]; then
  python3 "$APP_DIR/scripts/check-env-keys.py" >/dev/null 2>&1 && rec PASS "check-env-keys" || rec FAIL "check-env-keys"
  bash "$ROOT/deploy/secret-scan.sh" >/dev/null 2>&1 && rec PASS "secret-scan" || rec FAIL "secret-scan" "см. /tmp/secret-scan.matches"
  bash "$ROOT/deploy/env-preflight.sh" >/dev/null 2>&1 && rec PASS "env-preflight" || rec FAIL "env-preflight"
else
  rec SKIP "локальные ворота" "не git-клон"
fi

# ---------- 6. отчёт ----------
{
  echo "# Staging-отчёт — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "- URL: \`$URL\`"
  echo "- Авто-проверки: ✅ $PASS · ❌ $FAIL · ⏭ $SKIP"
  echo ""
  echo "## Авто-часть"
  echo "$DETAILS"
  echo ""
  echo "## Ручной остаток (закрывает владелец)"
  echo ""
  echo "- [РУЧНОЕ] Скриншоты staging для каждого фильтра каталога (P1 очереди)"
  echo "- [РУЧНОЕ] Железо по blocks/BLOCK-11-hardware.md (ТСД, Zebra/Eltron, IP-принтер, APK на устройствах)"
  echo "- [РУЧНОЕ] Обмен с боевой 1С (POST /1c/stock, not_found, названия не затёрты)"
  echo "- [РУЧНОЕ] Боевые оплаты (ЮKassa/Т-Банк/CryptoBot — по одному тестовому платежу)"
  echo "- [РУЧНОЕ] Backup/restore на чистом VPS (./deploy/backup-drill.sh --db ... на тестовом)"
  echo "- [РУЧНОЕ] Staging-публикации провайдеров (по одной, dry-run → approve)"
  echo "- [РУЧНОЕ] Скриншоты без секретов приложить к отчёту (дата + окружение)"
  echo ""
  echo "Полный чек-лист: DEVELOPER-MANUAL-VALIDATION.md"
} > "$OUT"
echo ""
echo "Отчёт: $OUT"
[ "$FAIL" = 0 ] && { echo "Итог: все авто-проверки зелёные ✅"; exit 0; }
echo "Итог: FAIL=$FAIL ❌"; exit 1
