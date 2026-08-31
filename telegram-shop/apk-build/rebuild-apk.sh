#!/usr/bin/env bash
# ============================================================
#  Сборка Android-релиза «Склад» (WebView-обёртка PWA /warehouse/)
#  Запуск:  ./rebuild-apk.sh [URL_ПО_УМОЛЧАНИЮ]
#  Пример:  ./rebuild-apk.sh https://shop.ru/warehouse/
#  Без аргумента — при первом запуске приложение спросит адрес.
#  Скрипт не требует sudo: все инструменты ставятся в ~/.cache.
#  Результат: APK + AAB для публикации в сторах.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

DEFAULT_URL="${1:-}"
APP_VERSION="1.0.6"
APP_CODE="7"
APK_NAME="Sklad-${APP_VERSION}-release.apk"
AAB_NAME="Sklad-${APP_VERSION}-release.aab"
GRADLE_VER="8.2.1"
CACHE_BASE="${XDG_CACHE_HOME:-$HOME/.cache}/telegram-shop-apk"
SDK_ROOT="${ANDROID_SDK_ROOT:-${CACHE_BASE}/android-sdk}"
GRADLE_HOME="${GRADLE_HOME:-${CACHE_BASE}/gradle-${GRADLE_VER}}"
JDK_HOME="${JDK17_HOME:-${CACHE_BASE}/jdk-17}"
KEYSTORE_PASS="TgShop2026!"
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
  if [ ! -f keystore/telegramshop.keystore ]; then
    log "Создаю ключ подписи release..."
    mkdir -p keystore
    keytool -genkeypair -keystore keystore/telegramshop.keystore -alias telegramshop \
      -storepass "${KEYSTORE_PASS}" -keypass "${KEYSTORE_PASS}" \
      -dname "CN=Telegram Shop, OU=Sklad, O=TelegramShop, L=Riga, C=LV" \
      -keyalg RSA -keysize 2048 -validity 10000 >/dev/null 2>&1
  fi
}

generate_icons() {
  local icon_src="../warehouse/icon-512.png"
  if [ ! -f android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png ] && command -v python3 >/dev/null 2>&1; then
    log "Генерирую иконки из warehouse/icon-512.png..."
    python3 - "${icon_src}" <<'PY'
import os, sys
from PIL import Image
src = sys.argv[1]
if not os.path.exists(src):
    raise SystemExit('Нет иконки: ' + src)
img = Image.open(src).convert('RGBA').resize((512, 512), Image.LANCZOS)
sizes = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}
for dpi, px in sizes.items():
    d = f'android/app/src/main/res/mipmap-{dpi}'
    os.makedirs(d, exist_ok=True)
    img.resize((px, px), Image.LANCZOS).save(f'{d}/ic_launcher.png')
    img.resize((px, px), Image.LANCZOS).save(f'{d}/ic_launcher_round.png')
print('OK: иконки сгенерированы')
PY
  fi
}

build_release_artifacts() {
  log "Проверяю версию Android-приложения (${APP_VERSION} / code ${APP_CODE})..."
  grep -q "versionName \"${APP_VERSION}\"" android/app/build.gradle
  grep -q "versionCode ${APP_CODE}" android/app/build.gradle

  log "Собираю release APK и AAB..."
  pushd android >/dev/null
  "${GRADLE_HOME}/bin/gradle" assembleRelease bundleRelease -PwarehouseUrl="${DEFAULT_URL}" --no-daemon --console=plain
  popd >/dev/null

  mkdir -p ../apk ../aab
  rm -f ../apk/Sklad-*-release.apk ../aab/Sklad-*-release.aab

  local apk="android/app/build/outputs/apk/release/app-release.apk"
  local aab="android/app/build/outputs/bundle/release/app-release.aab"
  local out_apk="../apk/${APK_NAME}"
  local out_aab="../aab/${AAB_NAME}"
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
generate_icons
build_release_artifacts
