#!/usr/bin/env bash
set -euo pipefail
# Idempotent VPS deploy without Docker. Run as a user with sudo privileges.
ROOT="${DEPLOY_ROOT:-/opt/magazin-shop}"; BRANCH="${DEPLOY_BRANCH:-main}"; PYTHON="${PYTHON_BIN:-python3}"
REPO="${DEPLOY_REPO:-https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git}"
SERVICE="${DEPLOY_SERVICE:-magazin-shop}"
if [[ "${1:-}" == "--help" ]]; then echo "DEPLOY_ROOT=/opt/magazin-shop DEPLOY_DOMAIN=https://example.com $0"; exit 0; fi
command -v git >/dev/null || { echo 'git is required' >&2; exit 1; }
command -v "$PYTHON" >/dev/null || { echo "$PYTHON is required" >&2; exit 1; }
sudo mkdir -p "$ROOT"; sudo chown -R "$(id -u):$(id -g)" "$ROOT"
if [[ -d "$ROOT/.git" ]]; then git -C "$ROOT" fetch origin "$BRANCH"; git -C "$ROOT" checkout "$BRANCH"; git -C "$ROOT" reset --hard "origin/$BRANCH"; else git clone --branch "$BRANCH" --depth 1 "$REPO" "$ROOT"; fi
cd "$ROOT/telegram-shop"
"$PYTHON" -m venv "$ROOT/.venv"; "$ROOT/.venv/bin/python" -m pip install --upgrade pip; "$ROOT/.venv/bin/pip" install -r requirements.txt
[[ -f .env ]] || { cp .env.production.example .env; echo "Created $ROOT/telegram-shop/.env; fill secrets before restart."; }
sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<EOF
[Unit]
Description=Telegram Shop API
After=network.target
[Service]
User=$(id -un)
WorkingDirectory=$ROOT/telegram-shop
EnvironmentFile=$ROOT/telegram-shop/.env
ExecStart=$ROOT/.venv/bin/python bot.py
Restart=always
RestartSec=5
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload; sudo systemctl enable "$SERVICE"; sudo systemctl restart "$SERVICE"; sleep 2
curl -fsS --max-time 15 "http://127.0.0.1:${PORT:-8000}/health/ready" >/dev/null
if [[ -n "${DEPLOY_DOMAIN:-}" ]]; then "$ROOT/deploy/post-deploy-smoke.sh" "$DEPLOY_DOMAIN"; fi
echo "Deploy complete: $SERVICE at $ROOT"
