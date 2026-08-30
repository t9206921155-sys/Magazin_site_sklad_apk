#!/bin/bash
set -e
echo "=== Сборка APK (полноценное мобильное приложение) ==="
if command -v npx &> /dev/null; then
  echo "1. Установка зависимостей (npm install)"
  echo "2. Инициализация React Native (npx react-native init TelegramShop)"
  echo "3. Копирование экранов (mobile/src/screens/*.js) в src/screens/"
  echo "4. Копирование навигации (mobile/src/navigation.js) в src/navigation.js"
  echo "5. Сборка APK: npx react-native run-android --variant=release"
  echo "=== Для полноценного APK требуется Android Studio + SDK + React Native CLI ==="
else
  echo "npx не найден. Установите Node.js и React Native CLI."
fi
