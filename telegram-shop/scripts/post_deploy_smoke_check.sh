#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 https://example.com [expected_version]"
  exit 1
fi

BASE_URL="${1%/}"
EXPECTED_VERSION="${2:-1.0.6}"
FAILS=0

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
cyan() { printf '\033[36m%s\033[0m\n' "$*"; }

fetch_status() {
  local path="$1"
  local code
  code="$(curl -k -sS -o /tmp/arena_smoke_body.txt -w '%{http_code}' "$BASE_URL$path" 2>/tmp/arena_smoke_error.txt || true)"
  if [ -z "$code" ]; then
    : > /tmp/arena_smoke_body.txt
    code="000"
  fi
  printf '%s' "$code"
}

check_http_200() {
  local path="$1"
  local title="$2"
  local code
  code="$(fetch_status "$path")"
  if [ "$code" = "200" ]; then
    green "OK   [$title] $path -> HTTP 200"
  else
    red "FAIL [$title] $path -> HTTP $code"
    FAILS=$((FAILS + 1))
  fi
}

check_contains() {
  local path="$1"
  local title="$2"
  local needle="$3"
  local code
  code="$(fetch_status "$path")"
  local body
  body="$(cat /tmp/arena_smoke_body.txt || true)"
  if [ "$code" = "200" ] && printf '%s' "$body" | grep -Eqi "$needle"; then
    green "OK   [$title] $path contains '$needle'"
  else
    red "FAIL [$title] $path missing '$needle' or bad status ($code)"
    FAILS=$((FAILS + 1))
  fi
}

check_svg() {
  local path="$1"
  local title="$2"
  local code
  code="$(fetch_status "$path")"
  local body
  body="$(cat /tmp/arena_smoke_body.txt || true)"
  if [ "$code" = "200" ] && printf '%s' "$body" | grep -qi '<svg'; then
    green "OK   [$title] $path returned SVG"
  else
    red "FAIL [$title] $path did not return SVG (HTTP $code)"
    FAILS=$((FAILS + 1))
  fi
}

check_release_json() {
  local path="/api/releases/android"
  local code
  code="$(fetch_status "$path")"
  if [ "$code" != "200" ]; then
    red "FAIL [releases-json] $path -> HTTP $code"
    FAILS=$((FAILS + 1))
    return
  fi
  if EXPECTED_VERSION="$EXPECTED_VERSION" python3 - <<'PY'
import json
import os
from pathlib import Path
expected = os.environ['EXPECTED_VERSION']
body = Path('/tmp/arena_smoke_body.txt').read_text()
data = json.loads(body)
version = ''
for key in ('apk', 'aab'):
    item = data.get(key) or {}
    if item.get('version'):
        version = item['version']
        break
publication = data.get('publication') or {}
assert publication.get('package_id') == 'ru.telegramshop.sklad', publication.get('package_id')
assert version == expected, version
print(version)
PY
  then
    green "OK   [releases-json] /api/releases/android has version ${EXPECTED_VERSION} and package ru.telegramshop.sklad"
  else
    red "FAIL [releases-json] JSON does not match expected version/package"
    FAILS=$((FAILS + 1))
  fi
}

cyan "== Public pages =="
check_http_200 "/" "home"
check_http_200 "/warehouse/" "warehouse"
check_contains "/download/android" "android-download" "Android"
check_contains "/download/android/rustore" "android-rustore" "RuStore"
check_contains "/privacy" "privacy" "конф|privacy"

cyan "== Release endpoints =="
check_release_json
check_svg "/api/releases/android/qr.svg?mode=connect" "android-qr-connect"
check_svg "/api/releases/android/qr.svg?mode=setup" "android-qr-setup"

cyan "== Manual checks still required =="
echo "- APK install: telegram-shop/apk/Sklad-1.0.6-release.apk"
echo "- deep link: sklad://connect?..."
echo "- QR onboarding on device"
echo "- web scanner and native fallback scanner"
echo "- APK update check screen"

if [ "$FAILS" -gt 0 ]; then
  red "Smoke-check finished with ${FAILS} failure(s)."
  exit 1
fi

green "Smoke-check finished successfully."
