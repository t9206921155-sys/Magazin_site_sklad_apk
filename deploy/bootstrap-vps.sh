#!/usr/bin/env bash
# ============================================================
#  Telegram Shop — первичная установка на чистый Ubuntu/Debian VPS
#
#  Одна команда (DNS домена уже должен указывать на VPS):
#    sudo -E DEPLOY_DOMAIN=shop.ru LETSENCRYPT_EMAIL=admin@shop.ru \
#      SETUP_BOT_TOKEN=123:ABC SETUP_ADMIN_IDS=111 SETUP_YES=1 \
#      ./deploy/bootstrap-vps.sh
#  или через мастер:  sudo ./setup.sh --vps --domain shop.ru
#
#  Что делает:
#    1) пакеты (git, python, nginx, certbot), swap для слабых VPS;
#    2) клон/обновление репозитория, пользователь, venv, зависимости;
#    3) .env через deploy/setup-env.sh (SETUP_* или интерактивный мастер);
#    4) systemd-сервис, nginx, HTTPS (certbot, если задан email);
#    5) таймеры бэкапа + ротация + watchdog;
#    6) health-check и итоговая сводка.
#
#  Переменные: DEPLOY_ROOT (/opt/magazin-shop), DEPLOY_USER (magazin),
#    DEPLOY_DOMAIN (обязательно), DEPLOY_REPO, LETSENCRYPT_EMAIL,
#    SETUP_* (см. deploy/setup-env.sh), SETUP_SKIP_HTTPS=1 (без certbot).
# ============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_ROOT_DIR="${DEPLOY_ROOT:-/opt/magazin-shop}"; APP_USER="${DEPLOY_USER:-magazin}"
DOMAIN="${DEPLOY_DOMAIN:-}"; EMAIL="${LETSENCRYPT_EMAIL:-}"
REPO="${DEPLOY_REPO:-https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git}"

usage(){ sed -n '2,/^# ===/p' "$0" | sed 's/^# \{0,1\}//'; }
log(){ printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✅\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  ⚠️\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m  ❌\033[0m %s\n' "$*" >&2; exit 1; }

for a in "$@"; do case "$a" in
  --dry-run) echo "DRY-RUN: bootstrap $DOMAIN в $DEPLOY_ROOT_DIR (6 шагов, см. --help)"; usage; exit 0 ;;
  --help|-h) usage; exit 0 ;;
  *) die "Неизвестный аргумент: $a" ;;
esac; done

[[ $EUID -eq 0 ]] || die "запуск только от root: sudo -E ..."
[ -n "$DOMAIN" ] || die "нужен DEPLOY_DOMAIN (или sudo ./setup.sh --vps --domain ...)"
DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"
export SETUP_DOMAIN="$DOMAIN"

# ---------- 1. пакеты и swap ----------
log "Устанавливаю системные пакеты"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip nginx curl certbot python3-certbot-nginx
ok "пакеты готовы"

# swap 2 ГБ для VPS с RAM < 2 ГБ (требование блока 18)
MEM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
if [ "$MEM_KB" -lt 2000000 ] && [ ! -f /swapfile ] && ! swapon --show | grep -q .; then
  log "RAM < 2 ГБ — создаю swap 2 ГБ"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  ok "swap включён"
fi
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q inactive; then
  ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
  ok "ufw: открыты ssh/80/443 (сам ufw не включаю — включите вручную: ufw enable)"
fi

# ---------- 2. код, пользователь, venv ----------
log "Код → $DEPLOY_ROOT_DIR"
if [ ! -d "$DEPLOY_ROOT_DIR/.git" ]; then git clone --depth 1 "$REPO" "$DEPLOY_ROOT_DIR";
else git -C "$DEPLOY_ROOT_DIR" fetch origin main && git -C "$DEPLOY_ROOT_DIR" reset --hard origin/main; fi
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$DEPLOY_ROOT_DIR" --shell /usr/sbin/nologin "$APP_USER"
chown -R "$APP_USER:$APP_USER" "$DEPLOY_ROOT_DIR"
cd "$DEPLOY_ROOT_DIR/telegram-shop"
python3 -m venv "$DEPLOY_ROOT_DIR/.venv"
"$DEPLOY_ROOT_DIR/.venv/bin/pip" install -q --upgrade pip
"$DEPLOY_ROOT_DIR/.venv/bin/pip" install -q -r requirements.txt
ok "venv и зависимости готовы"

# ---------- 3. .env через мастер ----------
log "Настраиваю .env (мастер setup-env.sh)"
export TELEGRAM_SHOP_DIR="$DEPLOY_ROOT_DIR/telegram-shop"
SETUP_ARGS=()
[ ! -t 0 ] && SETUP_ARGS+=(--non-interactive)
bash "$ROOT/deploy/setup-env.sh" "${SETUP_ARGS[@]}"
chown "$APP_USER:$APP_USER" "$DEPLOY_ROOT_DIR/telegram-shop/.env"
chmod 600 "$DEPLOY_ROOT_DIR/telegram-shop/.env"

# ---------- 4. systemd + nginx + HTTPS ----------
log "systemd-сервис magazin-shop"
cat > /etc/systemd/system/magazin-shop.service <<EOF
[Unit]
Description=Telegram Shop
After=network-online.target
Wants=network-online.target
[Service]
User=$APP_USER
WorkingDirectory=$DEPLOY_ROOT_DIR/telegram-shop
EnvironmentFile=$DEPLOY_ROOT_DIR/telegram-shop/.env
UMask=027
ExecStart=$DEPLOY_ROOT_DIR/.venv/bin/python bot.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/nginx/sites-available/magazin-shop <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 25M;
    location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-Proto \$scheme; }
}
EOF
ln -sf /etc/nginx/sites-available/magazin-shop /etc/nginx/sites-enabled/magazin-shop
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl daemon-reload && systemctl enable --now magazin-shop && systemctl reload nginx
ok "сервис запущен"

if [ -z "${SETUP_SKIP_HTTPS:-}" ] && [ -n "$EMAIL" ] && command -v certbot >/dev/null; then
  log "Выпускаю HTTPS-сертификат"
  certbot --nginx --non-interactive --agree-tos -m "$EMAIL" -d "$DOMAIN" --redirect \
    && ok "HTTPS включён" || warn "certbot не удался — проверьте DNS и запустите вручную"
elif [ -z "${SETUP_SKIP_HTTPS:-}" ]; then
  warn "LETSENCRYPT_EMAIL не задан — HTTPS пропущен (потом: certbot --nginx -d $DOMAIN)"
fi

# ---------- 5. бэкапы и watchdog ----------
log "Таймеры бэкапа и watchdog"
for unit in magazin-backup.service magazin-backup.timer magazin-backup-retention.service magazin-backup-retention.timer magazin-watchdog.service; do
  [ -f "$DEPLOY_ROOT_DIR/deploy/$unit" ] && cp "$DEPLOY_ROOT_DIR/deploy/$unit" /etc/systemd/system/
done
systemctl daemon-reload
systemctl enable --now magazin-backup.timer 2>/dev/null || warn "magazin-backup.timer не встал — проверьте юниты"
systemctl enable --now magazin-backup-retention.timer 2>/dev/null || true
systemctl enable --now magazin-watchdog.service 2>/dev/null || true
ok "таймеры включены"

# ---------- 6. проверка и сводка ----------
curl -fsS --max-time 15 "http://127.0.0.1:8000/health/ready" >/dev/null \
  && ok "health/ready: OK" || die "сервис не отвечает — journalctl -u magazin-shop -n 100"

log "Готово 🎉"
echo "  Сайт:      https://$DOMAIN/"
echo "  Админка:   https://$DOMAIN/admin"
echo "  Склад:     https://$DOMAIN/warehouse/  (admin / ADMIN_PASSWORD из .env)"
echo "  APK Склад:   https://$DOMAIN/download/android"
echo "  APK Магазин: https://$DOMAIN/download/app"
echo "  .env:      $DEPLOY_ROOT_DIR/telegram-shop/.env"
echo "  Логи:      journalctl -u magazin-shop -f"
echo ""
echo "  Дальше:"
echo "    1. ./deploy/post-deploy-smoke.sh https://$DOMAIN"
echo "    2. python3 $DEPLOY_ROOT_DIR/telegram-shop/scripts/setup_bot.py  (Telegram: команды, кнопка, тест)"
echo "    3. $DEPLOY_ROOT_DIR/deploy/build-apps.sh --url https://$DOMAIN  (сборка APK с адресом)"
echo "    4. DEVELOPER-MANUAL-VALIDATION.md — ручная приёмка перед боем"
