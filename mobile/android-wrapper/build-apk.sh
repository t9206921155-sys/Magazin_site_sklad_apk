#!/usr/bin/env bash
# ============================================================
#  Сборка Android-релиза «Магазин» — покупательская WebView-обёртка
#  витрины (блок 25, Фаза 1). Запуск:
#     ./build-apk.sh [URL_ВИТРИНЫ]
#  Пример:
#     ./build-apk.sh https://shop.ru/
#  Без аргумента — при первом запуске приложение спросит адрес.
#  Подпись: общий keystore «Склада» (решение владельца, Фаза 0).
#  Инструменты ставятся в ~/.cache, sudo не нужен.
#  Результат: telegram-shop/apk/Shop-<вер>-release.apk + .aab
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

DEFAULT_URL="${1:-}"
APP_VERSION="1.0.0"
APP_CODE="1"
APK_NAME="Shop-${APP_VERSION}-release.apk"
AAB_NAME="Shop-${APP_VERSION}-release.aab"
GRADLE_VER="8.2.1"
CACHE_BASE="${XDG_CACHE_HOME:-$HOME/.cache}/telegram-shop-apk"
SDK_ROOT="${ANDROID_SDK_ROOT:-${CACHE_BASE}/android-sdk}"
# Пин Gradle как у складской сборки: системный Gradle 9.x на Actions
# несовместим с AGP 8.x.
GRADLE_HOME="${CACHE_BASE}/gradle-${GRADLE_VER}"
JDK_HOME="${JDK17_HOME:-${CACHE_BASE}/jdk-17}"
KEYSTORE_PASS="TgShop2026!"
KEYSTORE_PATH="../../telegram-shop/apk-build/keystore/telegramshop.keystore"
CMDLINE_TOOLS_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
JDK_URL="https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse"

log() { echo -e "\n\033[1;36m==>\033[0m $*"; }

current_java_major() {
  if ! command -v javac >/dev/null 2>&1; then
    echo 0
    return
  fi
  javac -version 2>&1 | awk '{print $2}' | awk -F. '{ if ($1 == 1) print $2; else print $1; }'
}

ensure_jdk17() {
  local major
  major="$(current_java_major)"
  if [ "${major}" -ge 17 ]; then
    export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
  else
    if [ ! -x "${JDK_HOME}/bin/javac" ]; then
      log "Скачиваю JDK 17 в ${JDK_HOME}..."
      mkdir -p "${CACHE_BASE}"
      rm -rf "${JDK_HOME}" "${CACHE_BASE}/jdk17-download"
      mkdir -p "${CACHE_BASE}/jdk17-download"
      curl -LfsS "${JDK_URL}" -o "${CACHE_BASE}/jdk17.tar.gz"
      tar -xzf "${CACHE_BASE}/jdk17.tar.gz" -C "${CACHE_BASE}/jdk17-download"
      local extracted
      extracted="$(find "${CACHE_BASE}/jdk17-download" -mindepth 1 -maxdepth 1 -type d | head -1)"
      mv "${extracted}" "${JDK_HOME}"
      rm -rf "${CACHE_BASE}/jdk17-download"
    fi
    export JAVA_HOME="${JDK_HOME}"
  fi
  export PATH="${JAVA_HOME}/bin:${PATH}"
  log "JDK: $(java -version 2>&1 | head -1)"
}

ensure_sdk() {
  if [ ! -x "${SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager" ]; then
    log "Скачиваю Android command-line tools..."
    mkdir -p "${SDK_ROOT}/cmdline-tools" "${CACHE_BASE}"
    rm -rf "${CACHE_BASE}/cmdline-tools" "${SDK_ROOT}/cmdline-tools/latest"
    curl -LfsS "${CMDLINE_TOOLS_URL}" -o "${CACHE_BASE}/cmdtools.zip"
    unzip -q -o "${CACHE_BASE}/cmdtools.zip" -d "${CACHE_BASE}/cmdline-tools"
    mkdir -p "${SDK_ROOT}/cmdline-tools/latest"
    cp -R "${CACHE_BASE}/cmdline-tools/cmdline-tools/." "${SDK_ROOT}/cmdline-tools/latest/"
  fi
  export ANDROID_HOME="${SDK_ROOT}"
  export ANDROID_SDK_ROOT="${SDK_ROOT}"
  export PATH="${SDK_ROOT}/platform-tools:${PATH}"
  local sm="${SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager"
  log "Устанавливаю платформы Android (platform-tools, android-34, build-tools 34.0.0)..."
  yes | "${sm}" --sdk_root="${SDK_ROOT}" --licenses >/dev/null || true
  "${sm}" --sdk_root="${SDK_ROOT}" "platform-tools" "platforms;android-34" "build-tools;34.0.0" >/dev/null
}

ensure_gradle() {
  if [ ! -x "${GRADLE_HOME}/bin/gradle" ]; then
    log "Скачиваю Gradle ${GRADLE_VER}..."
    mkdir -p "${CACHE_BASE}"
    curl -LfsS "https://services.gradle.org/distributions/gradle-${GRADLE_VER}-bin.zip" -o "${CACHE_BASE}/gradle.zip"
    rm -rf "${CACHE_BASE}/gradle-tmp" "${GRADLE_HOME}"
    mkdir -p "${CACHE_BASE}/gradle-tmp"
    unzip -q -o "${CACHE_BASE}/gradle.zip" -d "${CACHE_BASE}/gradle-tmp"
    mv "${CACHE_BASE}/gradle-tmp/gradle-${GRADLE_VER}" "${GRADLE_HOME}"
    rm -rf "${CACHE_BASE}/gradle-tmp"
  fi
  export PATH="${GRADLE_HOME}/bin:${PATH}"
  log "Gradle: $("${GRADLE_HOME}/bin/gradle" --version | awk '/^Gradle /{print $2; exit}')"
}

ensure_keystore() {
  # Общий ключ со «Складом»: если складской keystore уже есть — используем его.
  if [ ! -f "${KEYSTORE_PATH}" ]; then
    log "Создаю общий ключ подписи (как у «Склада»)..."
    mkdir -p "$(dirname "${KEYSTORE_PATH}")"
    keytool -genkeypair -keystore "${KEYSTORE_PATH}" -alias telegramshop \
      -storepass "${KEYSTORE_PASS}" -keypass "${KEYSTORE_PASS}" \
      -dname "CN=Telegram Shop, OU=Sklad, O=TelegramShop, L=Riga, C=LV" \
      -keyalg RSA -keysize 2048 -validity 10000 >/dev/null 2>&1
  fi
}

build_release_artifacts() {
  log "Проверяю версию приложения (${APP_VERSION} / code ${APP_CODE})..."
  grep -q "versionName \"${APP_VERSION}\"" app/build.gradle
  grep -q "versionCode ${APP_CODE}" app/build.gradle

  log "Собираю release APK и AAB..."
  pushd app >/dev/null
  # gradle вызывается из app/ — путь к keystore в build.gradle относительный от app/
  "${GRADLE_HOME}/bin/gradle" assembleRelease bundleRelease -PshopUrl="${DEFAULT_URL}" --no-daemon --console=plain
  popd >/dev/null

  mkdir -p ../../telegram-shop/apk ../../telegram-shop/aab
  rm -f ../../telegram-shop/apk/Shop-*-release.apk ../../telegram-shop/aab/Shop-*-release.aab

  local apk="app/build/outputs/apk/release/app-release.apk"
  local aab="app/build/outputs/bundle/release/app-release.aab"
  local out_apk="../../telegram-shop/apk/${APK_NAME}"
  local out_aab="../../telegram-shop/aab/${AAB_NAME}"
  cp -f "${apk}" "${out_apk}"
  cp -f "${aab}" "${out_aab}"

  local bt="${SDK_ROOT}/build-tools/34.0.0"
  if [ -x "${bt}/apksigner" ]; then
    log "Проверка подписи APK:"
    "${bt}/apksigner" verify --print-certs "${out_apk}" | head -3 || true
  fi
  if command -v jarsigner >/dev/null 2>&1; then
    log "Проверка подписи AAB:"
    jarsigner -verify -certs "${out_aab}" >/dev/null && echo "AAB signature: OK"
  fi
  if [ -x "${bt}/aapt" ]; then
    log "Информация об APK:"
    "${bt}/aapt" dump badging "${out_apk}" | grep -E "^package|sdkVersion|targetSdkVersion|application-label:" || true
  fi
  echo -e "\n\033[1;32mГОТОВО APK:\033[0m ${out_apk}  ($(du -h "${out_apk}" | cut -f1))"
  echo -e "\033[1;32mГОТОВО AAB:\033[0m ${out_aab}  ($(du -h "${out_aab}" | cut -f1))"
}

ensure_jdk17
ensure_sdk
ensure_gradle
ensure_keystore
build_release_artifacts
