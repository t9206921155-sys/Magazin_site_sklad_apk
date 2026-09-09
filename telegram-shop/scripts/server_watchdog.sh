#!/usr/bin/env bash
# Watchdog сервера склада (блок 15).
# Проверяет /health/live и свободное место на диске; при сбоях шлёт
# Telegram-уведомление (BOT_TOKEN + ADMIN_IDS) и пишет в syslog.
#
# Запуск: ./scripts/server_watchdog.sh [base_url]
# Env:    BOT_TOKEN, ADMIN_IDS, DISK_FREE_MIN_MB (default 500), INTERVAL (default 30),
#         FAIL_THRESHOLD (default 3), DATA_DIR (default рядом со скриптом ../data)
#
# Для автозапуска см. deploy/magazin-watchdog.service (systemd перезапускает сервер).

set -u
URL="${1:-http://127.0.0.1:8000/health/live}"
INTERVAL="${INTERVAL:-30}"
FAIL_THRESHOLD="${FAIL_THRESHOLD:-3}"
DISK_FREE_MIN_MB="${DISK_FREE_MIN_MB:-500}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-$SCRIPT_DIR/../data}"

fails=0
notified_down=0
last_disk_notify=0

notify() {
  local text="$1"
  logger -t shop-watchdog "$text"
  echo "$(date '+%F %T') $text"
  if [ -n "${BOT_TOKEN:-}" ] && [ -n "${ADMIN_IDS:-}" ]; then
    for chat in ${ADMIN_IDS//,/ }; do
      curl -s -o /dev/null --max-time 10 \
        "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${chat}" \
        --data-urlencode "text=🚨 shop-watchdog: ${text}" >/dev/null 2>&1
    done
  fi
}

while true; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL" 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then
    if [ "$notified_down" = "1" ]; then
      notify "сервер восстановился (health 200)"
      notified_down=0
    fi
    fails=0
  else
    fails=$((fails + 1))
    if [ "$fails" -ge "$FAIL_THRESHOLD" ] && [ "$notified_down" = "0" ]; then
      notify "сервер недоступен: HTTP ${code}, ${fails} подряд (URL ${URL})"
      notified_down=1
    fi
  fi

  now=$(date +%s)
  if [ -d "$DATA_DIR" ] && [ $((now - last_disk_notify)) -ge 3600 ]; then
    free_mb=$(df -Pm "$DATA_DIR" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$free_mb" ] && [ "$free_mb" -lt "$DISK_FREE_MIN_MB" ]; then
      notify "мало места на диске: свободно ${free_mb} МБ (порог ${DISK_FREE_MIN_MB} МБ), путь ${DATA_DIR}"
      last_disk_notify=$now
    fi
  fi

  sleep "$INTERVAL"
done
