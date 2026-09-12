#!/usr/bin/env bash
# ============================================================
#  Telegram Shop — мастер настройки .env («из коробки»)
#
#  Интерактивно (есть TTY) или неинтерактивно (флаги / SETUP_*
#  переменные) создаёт telegram-shop/.env: генерирует секреты,
#  выводит доменные настройки из одного домена, валидирует ввод.
#  Секреты в выводе маскируются; .env пишется атомарно, chmod 600.
#
#  Запуск:
#    ./deploy/setup-env.sh                        # интерактивный мастер
#    ./deploy/setup-env.sh --non-interactive      # только флаги/SETUP_* + дефолты
#    ./deploy/setup-env.sh --check                # проверить существующий .env
#    ./deploy/setup-env.sh --dry-run              # показать, что будет записано
#    ./deploy/setup-env.sh --force ...            # перезаписать существующий .env
#
#  Флаги значений (приоритет над SETUP_*):
#    --domain shop.ru --bot-token 123:ABC --admin-ids 111,222
#    --admin-password s3cret --payment test --bot-mode polling
#    --webapp-url https://shop.ru --host 0.0.0.0 --port 8000
#
#  Переменные окружения: SETUP_DOMAIN, SETUP_BOT_TOKEN, SETUP_ADMIN_IDS,
#    SETUP_ADMIN_PASSWORD, SETUP_PAYMENT_PROVIDER, SETUP_BOT_MODE,
#    SETUP_WEBAPP_URL, SETUP_HOST, SETUP_PORT, SETUP_YES=1.
#  Служебные: TELEGRAM_SHOP_DIR (каталог приложения),
#    SETUP_ENV_FILE (путь к .env — для тестов).
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${TELEGRAM_SHOP_DIR:-$ROOT/telegram-shop}"
ENV_FILE="${SETUP_ENV_FILE:-$APP_DIR/.env}"

NONINTERACTIVE=0; FORCE=0; CHECK_ONLY=0; DRY_RUN=0
DOMAIN="${SETUP_DOMAIN:-}"; BOT_TOKEN="${SETUP_BOT_TOKEN:-}"
ADMIN_IDS="${SETUP_ADMIN_IDS:-}"; ADMIN_PASSWORD="${SETUP_ADMIN_PASSWORD:-}"
PAYMENT="${SETUP_PAYMENT_PROVIDER:-test}"; BOT_MODE="${SETUP_BOT_MODE:-polling}"
WEBAPP_URL="${SETUP_WEBAPP_URL:-}"; HOST_V="${SETUP_HOST:-0.0.0.0}"; PORT_V="${SETUP_PORT:-8000}"
[ "${SETUP_YES:-0}" = "1" ] && NONINTERACTIVE=1

usage(){ sed -n '2,/^# ===/p' "$0" | sed 's/^# \{0,1\}//'; }
log(){ printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✅\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  ⚠️\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m  ❌\033[0m %s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do case "$1" in
  --non-interactive|--yes|-y) NONINTERACTIVE=1; shift ;;
  --force) FORCE=1; shift ;;
  --check) CHECK_ONLY=1; shift ;;
  --dry-run) DRY_RUN=1; shift ;;
  --domain) DOMAIN="${2:-}"; shift 2 ;;
  --bot-token) BOT_TOKEN="${2:-}"; shift 2 ;;
  --admin-ids) ADMIN_IDS="${2:-}"; shift 2 ;;
  --admin-password) ADMIN_PASSWORD="${2:-}"; shift 2 ;;
  --payment) PAYMENT="${2:-}"; shift 2 ;;
  --bot-mode) BOT_MODE="${2:-}"; shift 2 ;;
  --webapp-url) WEBAPP_URL="${2:-}"; shift 2 ;;
  --host) HOST_V="${2:-}"; shift 2 ;;
  --port) PORT_V="${2:-}"; shift 2 ;;
  --help|-h) usage; exit 0 ;;
  *) die "Неизвестный аргумент: $1 (--help для справки)" ;;
esac; done

mask(){ # mask <secret> -> первые 4 символа + **** (пусто -> «не задан»)
  local s="${1:-}"
  [ -z "$s" ] && { echo "не задан"; return; }
  [ "${#s}" -le 8 ] && { echo "****"; return; }
  echo "${s:0:4}****"
}
gen_hex(){ python3 -c 'import secrets; print(secrets.token_hex(16))'; }
gen_pass(){ python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("".join(secrets.choice(a) for _ in range(16)))'; }

valid_token(){ [[ "${1:-}" =~ ^[0-9]{5,}:[A-Za-z0-9_-]{20,}$ ]]; }
valid_ids(){ [[ "${1:-}" =~ ^[0-9]+(,[0-9]+)*$ ]]; }
valid_payment(){ case "$1" in test|yookassa|tbank|cryptobot|stars) return 0;; *) return 1;; esac; }
valid_mode(){ case "$1" in polling|webhook) return 0;; *) return 1;; esac; }

norm_domain(){ # "https://shop.ru/" -> "shop.ru"
  local d="$1"
  d="${d#http://}"; d="${d#https://}"; d="${d%%/*}"
  echo "$d" | tr -d '[:space:]'
}

read_secret(){ # read_secret <var> <prompt> — ввод без эха, пусто = оставить
  local var="$1" prompt="$2" val=""
  printf '%s' "$prompt" >&2
  if [ -t 0 ]; then stty -echo 2>/dev/null || true; fi
  IFS= read -r val || true
  if [ -t 0 ]; then stty echo 2>/dev/null || true; echo >&2; fi
  printf '%s' "$val"
}

# ---------- режим --check: только валидация существующего .env ----------
if [ "$CHECK_ONLY" = 1 ]; then
  [ -f "$ENV_FILE" ] || die "нет файла $ENV_FILE — сначала запустите мастер без --check"
  fails=0
  get(){ grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }
  for k in BOT_TOKEN ADMIN_IDS ADMIN_PASSWORD WEBAPP_URL PAYMENT_PROVIDER BOT_MODE WEBHOOK_PATH \
           WEBHOOK_SECRET HOST PORT CORS_ORIGINS METRICS_TOKEN AUTH_RATE_LIMIT TRUSTED_HOSTS \
           RATE_LIMIT_1C RATE_LIMIT_API WH_SESSION_TTL_DAYS DISK_FREE_MIN_MB; do
    grep -Eq "^$k=" "$ENV_FILE" || { echo "  ❌ нет ключа $k" >&2; fails=1; }
  done
  grep -Eq 'PASTE_|CHANGE_ME|YOUR-DOMAIN|GENERATE_RANDOM' "$ENV_FILE" && { echo "  ❌ в .env остались плейсхолдеры" >&2; fails=1; }
  t="$(get BOT_TOKEN)"; [ -n "$t" ] && ! valid_token "$t" && { echo "  ❌ BOT_TOKEN не похож на токен Telegram" >&2; fails=1; }
  i="$(get ADMIN_IDS)"; [ -n "$i" ] && ! valid_ids "$i" && { echo "  ❌ ADMIN_IDS: нужны числа через запятую" >&2; fails=1; }
  p="$(get PAYMENT_PROVIDER)"; valid_payment "$p" || { echo "  ❌ PAYMENT_PROVIDER=$p недопустим" >&2; fails=1; }
  m="$(get BOT_MODE)"; valid_mode "$m" || { echo "  ❌ BOT_MODE=$m недопустим" >&2; fails=1; }
  [ "$fails" = 0 ] && { ok ".env корректен: $ENV_FILE"; exit 0; }
  die "проверка .env не пройдена"
fi

# ---------- существующий .env ----------
if [ -f "$ENV_FILE" ] && [ "$FORCE" = 0 ] && [ "$DRY_RUN" = 0 ]; then
  if grep -Eq 'PASTE_|CHANGE_ME|YOUR-DOMAIN|GENERATE_RANDOM' "$ENV_FILE"; then
    warn "в $ENV_FILE есть плейсхолдеры — перезаписываю значениями мастера"
  else
    ok ".env уже настроен — не трогаю (для перезаписи: --force)"
    exit 0
  fi
fi

# ---------- интерактивный ввод ----------
INTERACTIVE=0
[ "$NONINTERACTIVE" = 0 ] && [ -t 0 ] && INTERACTIVE=1

if [ "$INTERACTIVE" = 1 ]; then
  log "Мастер настройки Telegram Shop (Enter — оставить предложенное)"
  printf 'Домен магазина (пусто — локальный запуск без домена) [%s]: ' "$DOMAIN" >&2
  IFS= read -r ans || true; [ -n "$ans" ] && DOMAIN="$ans"
  printf 'Токен бота от @BotFather (пусто — бот отключится, сайт будет работать): ' >&2
  ans="$(read_secret x '')"; [ -n "$ans" ] && BOT_TOKEN="$ans"
  printf 'Telegram ID администраторов через запятую (узнать: @userinfobot) [%s]: ' "${ADMIN_IDS:-пусто}" >&2
  IFS= read -r ans || true; [ -n "$ans" ] && ADMIN_IDS="$ans"
  printf 'Пароль веб-админки / складов (пусто — сгенерировать надёжный): ' >&2
  ans="$(read_secret x '')"; [ -n "$ans" ] && ADMIN_PASSWORD="$ans"
  printf 'Оплата [test|yookassa|tbank|cryptobot|stars] [%s]: ' "$PAYMENT" >&2
  IFS= read -r ans || true; [ -n "$ans" ] && PAYMENT="$ans"
  printf 'Режим бота [polling|webhook] [%s]: ' "$BOT_MODE" >&2
  IFS= read -r ans || true; [ -n "$ans" ] && BOT_MODE="$ans"
fi

# ---------- нормализация и валидация ----------
DOMAIN="$(norm_domain "$DOMAIN")"
BOT_TOKEN="$(echo "$BOT_TOKEN" | tr -d '[:space:]')"
ADMIN_IDS="$(echo "$ADMIN_IDS" | tr -d '[:space:]')"
BOT_MODE="$(echo "$BOT_MODE" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
PAYMENT="$(echo "$PAYMENT" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"

[ -n "$BOT_TOKEN" ] && ! valid_token "$BOT_TOKEN" && die "BOT_TOKEN не похож на токен Telegram (ожидается 123456:ABC...)"
[ -n "$ADMIN_IDS" ] && ! valid_ids "$ADMIN_IDS" && die "ADMIN_IDS: нужны числа через запятую, например 123456789,987654321"
valid_payment "$PAYMENT" || die "PAYMENT_PROVIDER=$PAYMENT недопустим (test|yookassa|tbank|cryptobot|stars)"
valid_mode "$BOT_MODE" || die "BOT_MODE=$BOT_MODE недопустим (polling|webhook)"

GENERATED_PASSWORD=0
if [ -z "$ADMIN_PASSWORD" ]; then ADMIN_PASSWORD="$(gen_pass)"; GENERATED_PASSWORD=1; fi
METRICS_TOKEN="$(gen_hex)"; WEBHOOK_SECRET="$(gen_hex)"

if [ -z "$WEBAPP_URL" ] && [ -n "$DOMAIN" ]; then WEBAPP_URL="https://$DOMAIN"; fi
if [ -n "$DOMAIN" ]; then CORS_ORIGINS="https://$DOMAIN"; TRUSTED_HOSTS="$DOMAIN";
else CORS_ORIGINS="*"; TRUSTED_HOSTS=""; fi

if [ "$BOT_MODE" = "webhook" ]; then
  case "$WEBAPP_URL" in https://*) : ;;
    *) warn "для webhook нужен https-домен — переключаюсь на polling"; BOT_MODE="polling" ;;
  esac
  [ -z "$BOT_TOKEN" ] && { warn "без BOT_TOKEN webhook невозможен — переключаюсь на polling"; BOT_MODE="polling"; }
fi

# ---------- запись ----------
content() { cat <<EOF
# Создано мастером deploy/setup-env.sh — $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Секреты только здесь и на сервере. НЕ коммитить в git!
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
ADMIN_PASSWORD=$ADMIN_PASSWORD
WEBAPP_URL=$WEBAPP_URL
PAYMENT_PROVIDER=$PAYMENT
BOT_MODE=$BOT_MODE
WEBHOOK_PATH=/tg/webhook
WEBHOOK_SECRET=$WEBHOOK_SECRET
HOST=$HOST_V
PORT=$PORT_V
CORS_ORIGINS=$CORS_ORIGINS
METRICS_TOKEN=$METRICS_TOKEN
AUTH_RATE_LIMIT=20
TRUSTED_HOSTS=$TRUSTED_HOSTS
RATE_LIMIT_1C=120
RATE_LIMIT_API=600
WH_SESSION_TTL_DAYS=30
DISK_FREE_MIN_MB=500
EOF
}

if [ "$DRY_RUN" = 1 ]; then
  log "DRY-RUN: в $ENV_FILE было бы записано (секреты замаскированы):"
  echo "BOT_TOKEN=$(mask "$BOT_TOKEN") ADMIN_IDS=${ADMIN_IDS:-не задан}"
  echo "ADMIN_PASSWORD=$(mask "$ADMIN_PASSWORD") WEBAPP_URL=${WEBAPP_URL:-не задан}"
  echo "PAYMENT_PROVIDER=$PAYMENT BOT_MODE=$BOT_MODE CORS_ORIGINS=$CORS_ORIGINS"
  echo "TRUSTED_HOSTS=${TRUSTED_HOSTS:-не задан} HOST=$HOST_V PORT=$PORT_V"
  exit 0
fi

mkdir -p "$(dirname "$ENV_FILE")"
tmp="$(mktemp "$(dirname "$ENV_FILE")/.env.XXXXXX")"
content > "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE"

log "Записан $ENV_FILE (chmod 600)"
echo "  BOT_TOKEN:      $(mask "$BOT_TOKEN")"
echo "  ADMIN_IDS:      ${ADMIN_IDS:-не задан}"
echo "  ADMIN_PASSWORD: $(mask "$ADMIN_PASSWORD")"
echo "  WEBAPP_URL:     ${WEBAPP_URL:-не задан (локальный режим)}"
echo "  PAYMENT:        $PAYMENT   BOT_MODE: $BOT_MODE"
if [ "$GENERATED_PASSWORD" = 1 ]; then
  warn "СГЕНЕРИРОВАН пароль админки — запишите сейчас, больше он показан не будет:"
  printf '  🔑 ADMIN_PASSWORD=%s\n' "$ADMIN_PASSWORD"
fi
[ -z "$BOT_TOKEN" ] && warn "BOT_TOKEN пуст — Telegram-бот отключится, сайт/склад/админка работают"
[ -z "$ADMIN_IDS" ] && warn "ADMIN_IDS пуст — уведомления админам и часть команд недоступны"
ok "готово"
