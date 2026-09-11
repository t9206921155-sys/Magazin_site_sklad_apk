#!/usr/bin/env bash
# ============================================================
#  CI-сборка покупательского Android-приложения «Магазин»
#  (блок 25 Фаза 1, Shop 1.0.0). Вызывается из run-tests.sh
#  ПОСЛЕ зелёных тестов, только на GitHub Actions (push).
#  В dev-песочнице нет доступа к dl.google.com / services.gradle.org.
#
#  Защита от цикла: если telegram-shop/apk/Shop-<версия>-release.apk
#  уже есть в коммите — выходим. Пушит артефакты в ветку от GITHUB_TOKEN.
# ============================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

if [ "${GITHUB_EVENT_NAME:-}" != "push" ] || [ -z "${GITHUB_REF_NAME:-}" ]; then
  echo "ci-build-shop-apk: не Actions/push — пропуск"; exit 0
fi

# читаем версию из шапки build-apk.sh
APP_VERSION="$(sed -n 's/^APP_VERSION="\([^"]*\)"/\1/p' "${ROOT}/mobile/android-wrapper/build-apk.sh" | head -1)"
APP_CODE="$(sed -n 's/^APP_CODE="\([^"]*\)"/\1/p' "${ROOT}/mobile/android-wrapper/build-apk.sh" | head -1)"
[ -n "${APP_VERSION}" ] || { echo "ci-build-shop-apk: не нашёл APP_VERSION"; exit 1; }

APK="telegram-shop/apk/Shop-${APP_VERSION}-release.apk"
AAB="telegram-shop/aab/Shop-${APP_VERSION}-release.aab"
if [ -f "${APK}" ] && [ -f "${AAB}" ]; then
  echo "ci-build-shop-apk: артефакты ${APP_VERSION} уже в репо — пропуск"; exit 0
fi

echo "ci-build-shop-apk: собираю Shop ${APP_VERSION} (code ${APP_CODE}) на раннере..."
cd "${ROOT}/mobile/android-wrapper"
./build-apk.sh
cd "${ROOT}"

if [ ! -f "${APK}" ] || [ ! -f "${AAB}" ]; then
  echo "ci-build-shop-apk: сборка не дала артефактов"; exit 1
fi

git config user.email "actions@github.com"
git config user.name "github-actions[bot]"
git add "${APK}" "${AAB}"
if git diff --cached --quiet; then
  echo "ci-build-shop-apk: нечего коммитить"; exit 0
fi
git commit -m "CI: артефакты Shop ${APP_VERSION} (APK+AAB) [skip ci]"
if git push origin "HEAD:${GITHUB_REF_NAME}"; then
  echo "ci-build-shop-apk: артефакты запушены в ${GITHUB_REF_NAME}"
else
  echo "ci-build-shop-apk: push артефактов отклонён (read-only GITHUB_TOKEN) — доставит workflow build-apk"
fi
