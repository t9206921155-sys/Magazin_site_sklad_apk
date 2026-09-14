#!/usr/bin/env bash
# ============================================================
#  Telegram Shop — сборка мобильных приложений «из коробки»
#
#  Собирает оба Android-приложения с зашитым адресом сервера:
#    «Склад»  (ru.telegramshop.sklad) — PWA /warehouse/
#    «Магазин» (ru.telegramshop.shop)  — витрина /
#  Проверяет артефакты (размер, SHA-256), печатает ссылки,
#  deep links и QR для подключения телефонов.
#
#  Запуск:
#    ./deploy/build-apps.sh --url https://shop.ru
#    ./deploy/build-apps.sh                  # URL из telegram-shop/.env
#    ./deploy/build-apps.sh --sklad-only     # только «Склад»
#    ./deploy/build-apps.sh --shop-only      # только «Магазин»
#    ./deploy/build-apps.sh --skip-build     # только отчёт по готовым APK
#    ./deploy/build-apps.sh --dry-run        # показать план без сборки
#
#  Переменные: SETUP_MOBILE_URL (= --url), TELEGRAM_SHOP_DIR.
#  Первая сборка скачивает JDK 17 + Android SDK в ~/.cache (~500 МБ).
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${TELEGRAM_SHOP_DIR:-$ROOT/telegram-shop}"

URL="${SETUP_MOBILE_URL:-}"
SKLAD_ONLY=0; SHOP_ONLY=0; SKIP_BUILD=0; DRY_RUN=0

usage(){ sed -n '2,/^# ===/p' "$0" | sed 's/^# \{0,1\}//'; }
log(){ printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✅\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  ⚠️\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m  ❌\033[0m %s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do case "$1" in
  --url) URL="${2:-}"; shift 2 ;;
  --sklad-only) SKLAD_ONLY=1; shift ;;
  --shop-only) SHOP_ONLY=1; shift ;;
  --skip-build) SKIP_BUILD=1; shift ;;
  --dry-run) DRY_RUN=1; shift ;;
  --help|-h) usage; exit 0 ;;
  *) die "Неизвестный аргумент: $1 (--help для справки)" ;;
esac; done

[ "$SKLAD_ONLY" = 1 ] && [ "$SHOP_ONLY" = 1 ] && die "--sklad-only и --shop-only взаимоисключают друг друга"

# URL из .env, если флаг не задан
if [ -z "$URL" ] && [ -f "$APP_DIR/.env" ]; then
  URL="$(grep -E '^WEBAPP_URL=' "$APP_DIR/.env" | head -1 | cut -d= -f2-)"
fi
URL="${URL%/}"
if [ "$DRY_RUN" = 0 ] && [ "$SKIP_BUILD" = 0 ]; then
  case "$URL" in http://*|https://*) : ;;
    *) die "нужен --url https://ваш-домен (или WEBAPP_URL в telegram-shop/.env)" ;;
  esac
fi

DO_SKLAD=1; DO_SHOP=1
[ "$SHOP_ONLY" = 1 ] && DO_SKLAD=0
[ "$SKLAD_ONLY" = 1 ] && DO_SHOP=0

SKLAD_SH="$APP_DIR/apk-build/rebuild-apk.sh"
SHOP_SH="$ROOT/mobile/android-wrapper/build-apk.sh"

sklad_ver(){ sed -n 's/^APP_VERSION="\([^"]*\)"/\1/p' "$SKLAD_SH" | head -1; }
shop_ver(){ sed -n 's/^APP_VERSION="\([^"]*\)"/\1/p' "$SHOP_SH" | head -1; }

if [ "$DRY_RUN" = 1 ]; then
  log "DRY-RUN: план сборки (URL: ${URL:-не задан})"
  [ "$DO_SKLAD" = 1 ] && echo "  • Склад v$(sklad_ver): $SKLAD_SH ${URL:-<без URL — спросит на телефоне>}"
  [ "$DO_SHOP" = 1 ] && echo "  • Магазин v$(shop_ver): $SHOP_SH ${URL:-<без URL — спросит на телефоне>}"
  echo "  Артефакты: telegram-shop/apk/*.apk + telegram-shop/aab/*.aab"
  exit 0
fi

if [ "$SKIP_BUILD" = 0 ]; then
  if [ "$DO_SKLAD" = 1 ]; then
    log "Собираю «Склад» v$(sklad_ver) (URL: $URL/warehouse/)…"
    bash "$SKLAD_SH" "$URL/warehouse/"
  fi
  if [ "$DO_SHOP" = 1 ]; then
    log "Собираю «Магазин» v$(shop_ver) (URL: $URL/)…"
    bash "$SHOP_SH" "$URL/"
  fi
fi

# ---------- отчёт ----------
log "Артефакты"
fails=0
report(){
  local file="$1" label="$2"
  if [ -f "$file" ]; then
    local size sha
    size="$(du -h "$file" | cut -f1)"
    sha="$(sha256sum "$file" | cut -c1-16)"
    ok "$label: $size  sha256:$sha…  ($file)"
  else
    echo "  ❌ $label: нет файла $file" >&2; fails=1
  fi
}
SV="$(sklad_ver)"; HV="$(shop_ver)"
[ "$DO_SKLAD" = 1 ] && report "$APP_DIR/apk/Sklad-${SV}-release.apk" "Склад $SV (APK)"
[ "$DO_SKLAD" = 1 ] && report "$APP_DIR/aab/Sklad-${SV}-release.aab" "Склад $SV (AAB)"
[ "$DO_SHOP" = 1 ] && report "$APP_DIR/apk/Shop-${HV}-release.apk" "Магазин $HV (APK)"
[ "$DO_SHOP" = 1 ] && report "$APP_DIR/aab/Shop-${HV}-release.aab" "Магазин $HV (AAB)"

if [ -n "$URL" ]; then
  log "Подключение телефонов (сервер: $URL)"
  echo "  Склад:   $URL/download/android   deep link: sklad://setup?url=$URL/warehouse/"
  echo "  Магазин: $URL/download/app       deep link: shop://connect?url=$URL/"
  # QR в терминале, если есть qrcode (необязательная зависимость)
  python3 - "$URL" 2>/dev/null <<'PY' || true
import sys
try:
    import qrcode
except ImportError:
    sys.exit(1)
url = sys.argv[1]
for name, link in (("СКЛАД", f"sklad://setup?url={url}/warehouse/"),
                   ("МАГАЗИН", f"shop://connect?url={url}/")):
    print(f"\n  QR {name}: {link}")
    qr = qrcode.QRCode(border=1)
    qr.add_data(link)
    qr.print_ascii(invert=True)
PY
fi

# сверка с сервером, если он доступен (не фатально)
if [ -n "$URL" ]; then
  srv="$(curl -ksS --max-time 8 "$URL/api/app/version" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version","?"))' 2>/dev/null || echo "?")"
  [ "$srv" != "?" ] && echo "  Сервер отдаёт Магазин v$srv (локальная сборка v$HV)"
fi

[ "$fails" = 0 ] && ok "готово" || die "не все артефакты на месте"
