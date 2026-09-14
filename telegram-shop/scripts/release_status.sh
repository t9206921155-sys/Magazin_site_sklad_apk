#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

SKLAD_VER="$(sed -n 's/^APP_VERSION="\([^"]*\)"/\1/p' telegram-shop/apk-build/rebuild-apk.sh | head -1)"
SHOP_VER="$(sed -n 's/^APP_VERSION="\([^"]*\)"/\1/p' mobile/android-wrapper/build-apk.sh | head -1)"
APK_PATH="telegram-shop/apk/Sklad-${SKLAD_VER:-1.1.0}-release.apk"
AAB_PATH="telegram-shop/aab/Sklad-${SKLAD_VER:-1.1.0}-release.aab"
SHOP_APK="telegram-shop/apk/Shop-${SHOP_VER:-1.0.0}-release.apk"
BUILD_FILE="telegram-shop/apk-build/android/app/build.gradle"

printf 'Branch: %s\n' "$(git branch --show-current)"
printf 'HEAD:   %s\n' "$(git rev-parse --short HEAD)"
printf 'Status: %s\n' "$(if [ -z "$(git status --porcelain)" ]; then echo clean; else echo dirty; fi)"

if [ -f "$BUILD_FILE" ]; then
  VERSION_NAME="$(grep -E 'versionName ' "$BUILD_FILE" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
  VERSION_CODE="$(grep -E 'versionCode ' "$BUILD_FILE" | head -1 | awk '{print $2}')"
  printf 'Android version: %s (code %s)\n' "$VERSION_NAME" "$VERSION_CODE"
fi

if [ -f "$APK_PATH" ]; then
  printf 'APK: %s\n' "$APK_PATH"
  sha256sum "$APK_PATH"
else
  printf 'APK: missing (%s)\n' "$APK_PATH"
fi

if [ -f "$AAB_PATH" ]; then
  printf 'AAB: %s\n' "$AAB_PATH"
  sha256sum "$AAB_PATH"
else
  printf 'AAB: missing (%s)\n' "$AAB_PATH"
fi

if [ -f "$SHOP_APK" ]; then
  printf 'Shop APK: %s\n' "$SHOP_APK"
  sha256sum "$SHOP_APK"
else
  printf 'Shop APK: missing (%s)\n' "$SHOP_APK"
fi

cat <<'EOF'

Key docs:
- telegram-shop/FINAL-RELEASE-HANDOFF.md
- telegram-shop/PROD-DEPLOY-QUICKSTART.md
- telegram-shop/MERGE-READY-PLAN.md
- telegram-shop/MERGE-COMMAND-BLOCK.md
- telegram-shop/RUSTORE-CARD-CHECKLIST.md
EOF
