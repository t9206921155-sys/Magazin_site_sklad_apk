#!/usr/bin/env bash
# ============================================================
#  Telegram Shop — установка «из коробки» (единая точка входа)
#
#  Сценарии:
#    ./setup.sh                         # локально: deps + мастер .env + запуск
#    sudo ./setup.sh --vps --domain shop.ru --bot-token 123:ABC --admin-ids 111
#                                       # VPS с нуля: всё + systemd + nginx +
#                                       # HTTPS + бэкапы + smoke (см. SETUP-AUTO.md)
#    ./setup.sh --update                # безопасное обновление на VPS
#    ./setup.sh --setup-bot             # только настройка Telegram-бота
#    ./setup.sh --build-apps --url https://shop.ru
#                                       # только сборка мобильных приложений
#    ./setup.sh --check                 # проверить установку (env, секреты, health)
#    ./setup.sh --dry-run               # показать план без изменений
#
#  Общие флаги: --non-interactive / --yes, --venv, --no-run, --test,
#    --domain, --bot-token, --admin-ids, --admin-password, --payment,
#    --bot-mode, --force (перезаписать .env), --help.
#  Все значения можно задать переменными: SETUP_DOMAIN, SETUP_BOT_TOKEN,
#  SETUP_ADMIN_IDS, SETUP_ADMIN_PASSWORD, SETUP_PAYMENT_PROVIDER, SETUP_BOT_MODE.
# ============================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/telegram-shop"

MODE="local"; NONINTERACTIVE=0; USE_VENV=0; DO_RUN=1; DO_TEST=0; FORCE_ENV=0; DRY_RUN=0
DOMAIN="${SETUP_DOMAIN:-}"; BOT_TOKEN="${SETUP_BOT_TOKEN:-}"; ADMIN_IDS="${SETUP_ADMIN_IDS:-}"
ADMIN_PASSWORD="${SETUP_ADMIN_PASSWORD:-}"; PAYMENT="${SETUP_PAYMENT_PROVIDER:-}"
BOT_MODE="${SETUP_BOT_MODE:-}"; MOBILE_URL="${SETUP_MOBILE_URL:-}"
[ "${SETUP_YES:-0}" = "1" ] && NONINTERACTIVE=1

usage(){ sed -n '2,/^# ===/p' "$0" | sed 's/^# \{0,1\}//'; }
log(){ printf '\n\033[1;36m==> \033[0m%s\n' "$*"; }
ok(){ printf '\033[1;32m  ✅\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  ⚠️\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m  ❌\033[0m %s\n' "$*" >&2; exit 1; }

pass_env=()
while [ "$#" -gt 0 ]; do case "$1" in
  --vps) MODE="vps"; shift ;;
  --update) MODE="update"; shift ;;
  --setup-bot) MODE="bot"; shift ;;
  --build-apps) MODE="apps"; shift ;;
  --check) MODE="check"; shift ;;
  --dry-run) DRY_RUN=1; shift ;;
  --non-interactive|--yes|-y) NONINTERACTIVE=1; shift ;;
  --venv) USE_VENV=1; shift ;;
  --no-run) DO_RUN=0; shift ;;
  --test) DO_TEST=1; shift ;;
  --force) FORCE_ENV=1; shift ;;
  --domain) DOMAIN="$2"; shift 2 ;;
  --bot-token) BOT_TOKEN="$2"; shift 2 ;;
  --admin-ids) ADMIN_IDS="$2"; shift 2 ;;
  --admin-password) ADMIN_PASSWORD="$2"; shift 2 ;;
  --payment) PAYMENT="$2"; shift 2 ;;
  --bot-mode) BOT_MODE="$2"; shift 2 ;;
  --url) MOBILE_URL="$2"; shift 2 ;;
  --help|-h) usage; exit 0 ;;
  *) die "Неизвестный аргумент: $1 (--help для справки)" ;;
esac; done

export SETUP_DOMAIN="$DOMAIN" SETUP_BOT_TOKEN="$BOT_TOKEN" SETUP_ADMIN_IDS="$ADMIN_IDS" \
  SETUP_ADMIN_PASSWORD="$ADMIN_PASSWORD" SETUP_MOBILE_URL="$MOBILE_URL"
[ -n "$PAYMENT" ] && export SETUP_PAYMENT_PROVIDER="$PAYMENT"
[ -n "$BOT_MODE" ] && export SETUP_BOT_MODE="$BOT_MODE"
[ "$NONINTERACTIVE" = 1 ] && export SETUP_YES=1

# ---------- общие шаги ----------
check_python(){
  command -v python3 >/dev/null || die "нужен python3: apt install python3 python3-pip python3-venv"
  PYVER="$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
  python3 - "$PYVER" <<'PY' || die "нужен Python 3.10+ (сейчас $PYVER)"
import sys; major, minor = sys.argv[1].split("."); sys.exit(0 if (int(major), int(minor)) >= (3, 10) else 1)
PY
  ok "python3 $PYVER"
}
setup_pip(){
  PYBIN=python3
  if [ "$USE_VENV" = 1 ] || [ -d "$ROOT/.venv" ]; then
    [ -d "$ROOT/.venv" ] || python3 -m venv "$ROOT/.venv"
    # shellcheck disable=SC1091
    source "$ROOT/.venv/bin/activate"
    PYBIN="$ROOT/.venv/bin/python"
    ok "venv: $ROOT/.venv"
  fi
  log "Ставлю зависимости (telegram-shop/requirements.txt)"
  "$PYBIN" -m pip install -q --upgrade pip 2>/dev/null || true
  # shellcheck disable=SC2086
  "$PYBIN" -m pip install -q -r "$APP/requirements.txt" --break-system-packages 2>/dev/null \
    || "$PYBIN" -m pip install -q -r "$APP/requirements.txt"
  ok "зависимости установлены"
}
run_env_wizard(){
  local args=()
  [ "$NONINTERACTIVE" = 1 ] && args+=(--non-interactive)
  [ "$FORCE_ENV" = 1 ] && args+=(--force)
  log "Настраиваю telegram-shop/.env"
  bash "$ROOT/deploy/setup-env.sh" "${args[@]}"
}
print_summary(){
  local base="http://localhost:${PORT:-8000}"
  [ -n "$DOMAIN" ] && base="https://$DOMAIN"
  log "Сводка установки"
  echo "  Сайт:      $base/"
  echo "  Каталог:   $base/catalog"
  echo "  Mini App:  $base/app"
  echo "  Админка:   $base/admin"
  echo "  Склад:     $base/warehouse/   (логин admin, пароль — ADMIN_PASSWORD из .env)"
  echo "  Продавец:  $base/seller"
  echo "  APK Склад:   $base/download/android"
  echo "  APK Магазин: $base/download/app"
  echo ""
  echo "  Дальше: SETUP-AUTO.md — бот, приложения, бэкапы, чек-лист приёмки."
}

# ============================ режимы ============================
if [ "$DRY_RUN" = 1 ] && [ "$MODE" = "local" ]; then
  log "DRY-RUN: локальный план"
  echo "  1. check_python + pip install requirements.txt"
  echo "  2. deploy/setup-env.sh (мастер .env)"
  echo "  3. scripts/check-env-keys.py"
  [ "$DO_TEST" = 1 ] && echo "  4. run-tests.sh"
  [ "$DO_RUN" = 1 ] && echo "  5. запуск: cd telegram-shop && python3 bot.py" || echo "  5. без запуска (--no-run)"
  bash "$ROOT/deploy/setup-env.sh" --dry-run $([ "$NONINTERACTIVE" = 1 ] && echo --non-interactive)
  exit 0
fi

case "$MODE" in
vps)
  [ "$EUID" -eq 0 ] || die "--vps требует root: sudo ./setup.sh --vps ..."
  [ -n "$DOMAIN" ] || die "--vps требует --domain (или SETUP_DOMAIN)"
  export DEPLOY_DOMAIN="$DOMAIN"
  log "VPS-установка на домен $DOMAIN"
  [ "$DRY_RUN" = 1 ] && { bash "$ROOT/deploy/bootstrap-vps.sh" --dry-run; exit 0; }
  bash "$ROOT/deploy/bootstrap-vps.sh"
  # Telegram-бот после деплоя (не фатально: токена может не быть)
  DEPLOYED_APP="${DEPLOY_ROOT:-/opt/magazin-shop}/telegram-shop"
  if [ -n "$BOT_TOKEN" ] && [ -f "$DEPLOYED_APP/scripts/setup_bot.py" ]; then
    python3 "$DEPLOYED_APP/scripts/setup_bot.py" \
      || warn "автонастройка бота не удалась — вручную: python3 $DEPLOYED_APP/scripts/setup_bot.py"
  fi
  print_summary
  ;;
update)
  [ "$DRY_RUN" = 1 ] && { bash "$ROOT/deploy/update.sh" --dry-run; exit 0; }
  bash "$ROOT/deploy/update.sh"
  ;;
bot)
  log "Настройка Telegram-бота"
  [ "$DRY_RUN" = 1 ] && { python3 "$APP/scripts/setup_bot.py" --dry-run; exit 0; }
  [ -f "$APP/.env" ] || die "нет telegram-shop/.env — сначала ./setup.sh (мастер создаст)"
  python3 "$APP/scripts/setup_bot.py"
  ;;
apps)
  [ "$DRY_RUN" = 1 ] && { bash "$ROOT/deploy/build-apps.sh" --dry-run ${MOBILE_URL:+--url "$MOBILE_URL"}; exit 0; }
  if [ -n "$MOBILE_URL" ]; then bash "$ROOT/deploy/build-apps.sh" --url "$MOBILE_URL";
  else bash "$ROOT/deploy/build-apps.sh"; fi
  ;;
check)
  log "Проверка установки"
  fails=0
  python3 "$APP/scripts/check-env-keys.py" || fails=1
  bash "$ROOT/deploy/setup-env.sh" --check || fails=1
  bash "$ROOT/deploy/secret-scan.sh" || fails=1
  # короткий boot + health на временной БД (не трогает боевую)
  if python3 -c 'import fastapi, uvicorn' 2>/dev/null; then
    TMP_DB="$(mktemp "${TMPDIR:-/tmp}/magazin-check-XXXXXX.db")"
    PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close())')"
    export MAGAZIN_DB="$TMP_DB" BOT_TOKEN= PORT
    python3 "$APP/bot.py" >"$TMP_DB.log" 2>&1 & PID=$!
    ok_boot=0
    for _ in $(seq 1 30); do curl -sf "http://127.0.0.1:$PORT/health/ready" >/dev/null && { ok_boot=1; break; }; sleep 1; done
    for u in /health/ready / /catalog /app /warehouse/ /sitemap.xml; do
      code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT$u")"
      [ "$code" = 200 ] && ok "GET $u → 200" || { echo "  ❌ GET $u → $code" >&2; fails=1; }
    done
    [ "$ok_boot" = 0 ] && { echo "  ❌ сервер не поднялся (лог: $TMP_DB.log)" >&2; fails=1; }
    kill "$PID" 2>/dev/null || true; rm -f "$TMP_DB" "$TMP_DB.log"
  else
    warn "зависимости не стоят — boot-проверка пропущена (./setup.sh --no-run для установки)"
  fi
  [ "$fails" = 0 ] && ok "проверка пройдена" || die "проверка не пройдена"
  ;;
local)
  log "Telegram Shop — установка «из коробки»"
  check_python
  setup_pip
  run_env_wizard
  python3 "$APP/scripts/check-env-keys.py" || warn "сверьте .env с config.py"
  if [ "$DO_TEST" = 1 ]; then
    log "Прогоняю тесты (run-tests.sh)"
    bash "$ROOT/run-tests.sh"
  fi
  # предложить настройку бота (только интерактивно и при наличии токена в .env)
  if [ "$NONINTERACTIVE" = 0 ] && [ -t 0 ] && grep -Eq '^BOT_TOKEN=[0-9]{5,}:' "$APP/.env" 2>/dev/null; then
    printf 'Настроить Telegram-бота сейчас (команды, кнопка меню, тест)? [Y/n]: ' >&2
    IFS= read -r ans || true
    case "$ans" in n|N|no|нет) warn "пропущено — позже: ./setup.sh --setup-bot" ;;
      *) python3 "$APP/scripts/setup_bot.py" || warn "не удалось — позже: ./setup.sh --setup-bot" ;;
    esac
  fi
  print_summary
  [ "$DO_RUN" = 0 ] && { log "Готово (--no-run). Запуск вручную: cd telegram-shop && python3 bot.py"; exit 0; }
  log "Запускаю сервер (Ctrl+C — остановить)"
  cd "$APP" && exec "$PYBIN" bot.py
  ;;
esac
