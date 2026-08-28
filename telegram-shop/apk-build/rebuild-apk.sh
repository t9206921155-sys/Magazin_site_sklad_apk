#!/usr/bin/env bash
# ============================================================
#  Сборка APK «Склад» (WebView-обёртка PWA /warehouse/)
#  Запуск:  ./rebuild-apk.sh [URL_ПО_УМОЛЧАНИЮ]
#  Пример:  ./rebuild-apk.sh https://shop.ru/warehouse/
#  Без аргумента — при первом запуске приложение спросит адрес.
#  Работает на Linux (Debian/Ubuntu) и macOS (brew).
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

DEFAULT_URL="${1:-}"
GRADLE_VER="8.7"
CMDTOOLS_ZIP="commandlinetools-linux-11076708_latest.zip"
SDK_ROOT="${ANDROID_SDK_ROOT:-/opt/android-sdk}"
GRADLE_HOME="/opt/gradle-${GRADLE_VER}"
KEYSTORE_PASS="TgShop2026!"

log() { echo -e "\n\033[1;36m==>\033[0m $*"; }

# ---------- JDK 17 ----------
if ! command -v javac >/dev/null 2>&1; then
  log "Устанавливаю JDK 17..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y -qq openjdk-17-jdk-headless
    sudo update-alternatives --set java "$(dirname "$(readlink -f "$(command -v java)")")/../bin/java" 2>/dev/null || true
  elif command -v brew >/dev/null 2>&1; then
    brew install --cask temurin@17 || brew install openjdk@17
  fi
fi
export JAVA_HOME="${JAVA_HOME:-$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")}"
log "JDK: $(java -version 2>&1 | head -1)"

# ---------- Android SDK ----------
if [ ! -x "${SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager" ]; then
  log "Скачиваю Android command-line tools..."
  sudo mkdir -p "${SDK_ROOT}/cmdline-tools"
  curl -fsSL -o /tmp/cmdtools.zip "https://dl.google.com/android/repository/${CMDTOOLS_ZIP}"
  sudo unzip -q -o /tmp/cmdtools.zip -d /tmp/cmdtools
  sudo mv /tmp/cmdtools/cmdline-tools "${SDK_ROOT}/cmdline-tools/latest"
fi
export ANDROID_HOME="${SDK_ROOT}"
SM="${SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager"
log "Устанавливаю платформы (android-34, build-tools 34.0.0)..."
yes | sudo -E "${SM}" --sdk_root="${SDK_ROOT}" --licenses >/dev/null 2>&1 || true
sudo -E "${SM}" --sdk_root="${SDK_ROOT}" "platform-tools" "platforms;android-34" "build-tools;34.0.0" >/dev/null

# ---------- Gradle ----------
if [ ! -x "${GRADLE_HOME}/bin/gradle" ]; then
  log "Скачиваю Gradle ${GRADLE_VER}..."
  curl -fsSL -o /tmp/gradle.zip "https://services.gradle.org/distributions/gradle-${GRADLE_VER}-bin.zip"
  sudo unzip -q -o /tmp/gradle.zip -d /opt
fi

# ---------- Ключ подписи ----------
if [ ! -f keystore/telegramshop.keystore ]; then
  log "Создаю ключ подписи release..."
  mkdir -p keystore
  keytool -genkeypair -keystore keystore/telegramshop.keystore -alias telegramshop \
    -storepass "${KEYSTORE_PASS}" -keypass "${KEYSTORE_PASS}" \
    -dname "CN=Telegram Shop, OU=Sklad, O=TelegramShop, L=Moscow, C=RU" \
    -keyalg RSA -keysize 2048 -validity 10000 2>/dev/null
fi

# ---------- Иконки ----------
ICON_SRC="../../warehouse/icon-512.png"
if [ ! -f android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png ] && command -v python3 >/dev/null 2>&1; then
  log "Генерирую иконки из warehouse/icon-512.png..."
  python3 - "${ICON_SRC}" <<'EOF'
import os, sys
from PIL import Image
src = sys.argv[1]
if not os.path.exists(src):
    sys.exit("Нет иконки: " + src)
img = Image.open(src).convert("RGBA").resize((512, 512), Image.LANCZOS)
sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
for dpi, px in sizes.items():
    d = f"android/app/src/main/res/mipmap-{dpi}"
    os.makedirs(d, exist_ok=True)
    img.resize((px, px), Image.LANCZOS).save(f"{d}/ic_launcher.png")
    img.resize((px, px), Image.LANCZOS).save(f"{d}/ic_launcher_round.png")
print("OK: иконки сгенерированы")
EOF
fi

# ---------- Сборка ----------
log "Собираю release APK (Gradle ${GRADLE_VER})..."
cd android
"${GRADLE_HOME}/bin/gradle" assembleRelease -PwarehouseUrl="${DEFAULT_URL}" --no-daemon --console=plain

# ---------- Результат ----------
mkdir -p ../../apk
APK="app/build/outputs/apk/release/app-release.apk"
OUT="../../apk/Sklad-1.0.0-release.apk"
cp -f "${APK}" "${OUT}"

BT="${SDK_ROOT}/build-tools/34.0.0"
if [ -x "${BT}/apksigner" ]; then
  log "Проверка подписи:"
  "${BT}/apksigner" verify --print-certs "${OUT}" | head -3
  log "Информация об APK:"
  "${BT}/aapt" dump badging "${OUT}" | grep -E "^package|sdkVersion|targetSdkVersion|application-label:"
fi
echo -e "\n\033[1;32mГОТОВО:\033[0m ${OUT}  ($(du -h "${OUT}" | cut -f1))"
echo "Переслать на телефон: Telegram-бот -> 'Сохранить в файлы' -> установить (разрешить неизвестные источники)."
