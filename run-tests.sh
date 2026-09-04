#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT/telegram-shop"
TMP_DB="$(mktemp -p "${TMPDIR:-/tmp}" magazin-tests-XXXXXX.db)"; LOG="${TMP_DB}.log"
cleanup(){ [[ -n "${PID:-}" ]] && kill "$PID" 2>/dev/null || true; rm -f "$TMP_DB" "$LOG"; }
trap cleanup EXIT
export MAGAZIN_DB="$TMP_DB" BOT_TOKEN= PORT=8000
python3 bot.py >"$LOG" 2>&1 & PID=$!
for i in {1..30}; do curl -sf http://127.0.0.1:8000/ >/dev/null && break; sleep 1; done
status=0
python3 tests-labels.py || status=1
node tests-hid-scanner.js || status=1
python3 tests-stage5.py || status=1
python3 tests-block06.py || status=1
python3 tests-block09.py || status=1
python3 -m py_compile *.py || status=1
for f in warehouse/*.js webapp/*.js; do node --check "$f" || status=1; done
exit "$status"
