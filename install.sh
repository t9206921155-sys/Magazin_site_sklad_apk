#!/usr/bin/env bash
# ============================================================
#  Telegram Shop — установка «из коробки» (локально или на VPS)
#
#  Что делает:
#   1) проверяет окружение (python3 3.10+, pip, git);
#   2) ставит зависимости из telegram-shop/requirements.txt;
#   3) создаёт telegram-shop/.env из шаблона (если его нет);
#   4) проверяет ключи .env и запускает тесты (опционально);
#   5) запускает сервер: http://0.0.0.0:8000
#
#  Запуск:   ./install.sh            # установка + запуск
#            ./install.sh --no-run   # только установить
#            ./install.sh --venv     # использовать venv (.venv)
#            ./install.sh --test     # прогнать тесты перед стартом
#
#  Для production-VPS (nginx, systemd, HTTPS) используйте:
#            sudo DEPLOY_DOMAIN=shop.example.com ./deploy/bootstrap-vps.sh
# ============================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/telegram-shop"
USE_VENV=0; DO_RUN=1; DO_TEST=0
for a in "$@"; do case "$a" in
  --venv) USE_VENV=1 ;; --no-run) DO_RUN=0 ;; --test) DO_TEST=1 ;;
  --help|-h) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Неизвестный аргумент: $a (--help для справки)"; exit 1 ;;
esac; done

log(){ printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✅\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  ⚠️\033[0m %s\n' "$*"; }

# ---------- 1. окружение ----------
log "Проверяю окружение"
command -v git >/dev/null || { echo "Нужен git: apt install git"; exit 1; }
command -v python3 >/dev/null || { echo "Нужен python3: apt install python3 python3-pip"; exit 1; }
PYVER="$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
python3 - "$PYVER" <<'PY' || { echo "Нужен Python 3.10+ (сейчас ${PYVER})"; exit 1; }
import sys; major, minor = sys.argv[1].split("."); sys.exit(0 if (int(major), int(minor)) >= (3, 10) else 1)
PY
ok "python3 ${PYVER}"
PYBIN=python3
if [ "$USE_VENV" = 1 ]; then
  [ -d "$ROOT/.venv" ] || python3 -m venv "$ROOT/.venv"
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
  PYBIN="$ROOT/.venv/bin/python"
  ok "venv: $ROOT/.venv"
fi

# ---------- 2. зависимости ----------
log "Ставлю зависимости (requirements.txt)"
"$PYBIN" -m pip install -q --upgrade pip 2>/dev/null || true
PIP_FLAGS=(-q -r "$APP/requirements.txt")
"$PYBIN" -m pip install "${PIP_FLAGS[@]}" --break-system-packages 2>/dev/null || "$PYBIN" -m pip install "${PIP_FLAGS[@]}"
ok "зависимости установлены"
warn "обработка видео ставится отдельно: pip install -r telegram-shop/requirements-video.txt (не обязательно)"

# ---------- 3. .env ----------
log "Настраиваю telegram-shop/.env"
if [ ! -f "$APP/.env" ]; then
  cp "$APP/.env.example" "$APP/.env"
  ok "создан .env из шаблона (.env.example)"
  warn "заполните минимум: BOT_TOKEN (от @BotFather), ADMIN_IDS, WEBAPP_URL"
else
  ok ".env уже существует — не трогаю"
fi
if "$PYBIN" "$APP/scripts/check-env-keys.py" >/dev/null 2>&1; then
  ok "все ключи .env задокументированы"
else
  warn "в .env.example не хватает ключей — сверьте с config.py"
fi
if grep -Eq '^(BOT_TOKEN=.+)' "$APP/.env"; then ok "BOT_TOKEN задан"; else warn "BOT_TOKEN пуст — бот отключится, сайт/склад работают и так"; fi

# ---------- 4. тесты (опционально) ----------
if [ "$DO_TEST" = 1 ]; then
  log "Прогоняю тесты (bash run-tests.sh)"
  bash "$ROOT/run-tests.sh"
fi

# ---------- 5. старт ----------
[ "$DO_RUN" = 0 ] && { log "Готово (--no-run): запуск вручную — cd telegram-shop && python3 bot.py"; exit 0; }
log "Запускаю сервер: http://0.0.0.0:${PORT:-8000}  (Ctrl+C — остановить)"
echo    "    сайт:      http://localhost:${PORT:-8000}/"
echo    "    склад:     http://localhost:${PORT:-8000}/warehouse/  (admin/admin123 — смените!)"
echo    "    админка:   http://localhost:${PORT:-8000}/admin"
echo    "    mini app:  http://localhost:${PORT:-8000}/app"
echo    "    APK:       http://localhost:${PORT:-8000}/download/android"
cd "$APP" && exec "$PYBIN" bot.py
