#!/usr/bin/env bash
set -euo pipefail
# First-time Ubuntu/Debian VPS bootstrap. Review before running on production.
ROOT="${DEPLOY_ROOT:-/opt/magazin-shop}"; APP_USER="${DEPLOY_USER:-magazin}"; DOMAIN="${DEPLOY_DOMAIN:-}"; EMAIL="${LETSENCRYPT_EMAIL:-}"
REPO="${DEPLOY_REPO:-https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git}"
[[ $EUID -eq 0 ]] || { echo 'Run as root: sudo -E ...' >&2; exit 1; }
[[ -n "$DOMAIN" ]] || { echo 'DEPLOY_DOMAIN is required' >&2; exit 1; }
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip nginx curl certbot python3-certbot-nginx
if [[ ! -d "$ROOT/.git" ]]; then git clone --depth 1 "$REPO" "$ROOT"; else git -C "$ROOT" fetch origin main && git -C "$ROOT" reset --hard origin/main; fi
if ! id "$APP_USER" >/dev/null 2>&1; then useradd --system --home "$ROOT" --shell /usr/sbin/nologin "$APP_USER"; fi
chown -R "$APP_USER:$APP_USER" "$ROOT"; cd "$ROOT/telegram-shop"
python3 -m venv "$ROOT/.venv"; "$ROOT/.venv/bin/pip" install -r requirements.txt
if [[ ! -f .env ]]; then cp .env.production.example .env; fi
if grep -Eq 'PASTE_|CHANGE_ME|YOUR-DOMAIN|GENERATE_RANDOM' .env; then echo "Fill $ROOT/telegram-shop/.env and rerun." >&2; exit 2; fi
cat > "/etc/systemd/system/magazin-shop.service" <<EOF
[Unit]
Description=Telegram Shop
After=network-online.target
Wants=network-online.target
[Service]
User=$APP_USER
WorkingDirectory=$ROOT/telegram-shop
EnvironmentFile=$ROOT/telegram-shop/.env
UMask=027
ExecStart=$ROOT/.venv/bin/python bot.py
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
nginx -t; systemctl daemon-reload; systemctl enable --now magazin-shop; systemctl reload nginx
if [[ -n "$EMAIL" ]] && command -v certbot >/dev/null; then certbot --nginx --non-interactive --agree-tos -m "$EMAIL" -d "$DOMAIN" --redirect; fi
curl -fsS --max-time 15 "http://127.0.0.1:8000/health/ready" >/dev/null
echo "Bootstrap complete. Run: $ROOT/deploy/post-deploy-smoke.sh https://$DOMAIN"
