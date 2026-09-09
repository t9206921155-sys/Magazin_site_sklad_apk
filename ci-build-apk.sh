#!/usr/bin/env bash
# ============================================================
#  CI-сборка Android-релиза «Склад» (блок 26, Sklad 1.1.0).
#  Вызывается из run-tests.sh ПОСЛЕ зелёных тестов, только на
#  GitHub Actions (push). В dev-песочнице нет доступа к
#  dl.google.com / services.gradle.org — там сборка не выполняется.
#
#  Защита от цикла: если telegram-shop/apk/Sklad-<версия>-release.apk
#  уже есть в коммите — считаем, что собрано, и выходим.
#  Пушит артефакты обратно в ветку от имени GITHUB_TOKEN.
# ============================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# run-tests.sh вызывает нас из telegram-shop/ — относительные пути должны
# считаться от корня репо, иначе проверка «артефакты уже в репо» не срабатывает
# и CI пересобирает APK на каждый пуш.
cd "${ROOT}"

# только на Actions, только для push
if [ "${GITHUB_EVENT_NAME:-}" != "push" ] || [ -z "${GITHUB_REF_NAME:-}" ]; then
  echo "ci-build-apk: не Actions/push — пропуск"; exit 0
fi

# читаем версию из шапки rebuild-apk.sh
APP_VERSION="$(sed -n 's/^APP_VERSION="\([^"]*\)"/\1/p' "${ROOT}/telegram-shop/apk-build/rebuild-apk.sh" | head -1)"
APP_CODE="$(sed -n 's/^APP_CODE="\([^"]*\)"/\1/p' "${ROOT}/telegram-shop/apk-build/rebuild-apk.sh" | head -1)"
[ -n "${APP_VERSION}" ] || { echo "ci-build-apk: не нашёл APP_VERSION"; exit 1; }

APK="telegram-shop/apk/Sklad-${APP_VERSION}-release.apk"
AAB="telegram-shop/aab/Sklad-${APP_VERSION}-release.aab"
if [ -f "${APK}" ] && [ -f "${AAB}" ]; then
  echo "ci-build-apk: артефакты ${APP_VERSION} уже в репо — пропуск"; exit 0
fi

echo "ci-build-apk: собираю Sklad ${APP_VERSION} (code ${APP_CODE}) на раннере..."
cd "${ROOT}/telegram-shop/apk-build"
./rebuild-apk.sh
cd "${ROOT}"

if [ ! -f "${APK}" ] || [ ! -f "${AAB}" ]; then
  echo "ci-build-apk: сборка не дала артефактов"; exit 1
fi

# коммитим артефакты в ветку (GITHUB_TOKEN уже настроен actions/checkout)
git config user.email "actions@github.com"
git config user.name "github-actions[bot]"
git add "${APK}" "${AAB}"
if git diff --cached --quiet; then
  echo "ci-build-apk: нечего коммитить"; exit 0
fi
git commit -m "CI: артефакты Sklad ${APP_VERSION} (APK+AAB) [skip ci]"
# Пуш артефактов отсюда — best-effort: если GITHUB_TOKEN read-only,
# доставку делает workflow build-apk (permissions: contents: write).
if git push origin "HEAD:${GITHUB_REF_NAME}"; then
  echo "ci-build-apk: артефакты запушены в ${GITHUB_REF_NAME}"
else
  echo "ci-build-apk: push артефактов отклонён (read-only GITHUB_TOKEN) — доставит workflow build-apk"
fi
