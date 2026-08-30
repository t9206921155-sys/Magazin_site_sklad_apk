# 🚀 PROD deploy quickstart — copy/paste

Короткая инструкция для выкладки ветки `arena/continue-marketplace-content` в production.

## Вариант A — Docker deploy из корня репозитория

```bash
cd /path/to/repo
git fetch origin
git checkout arena/continue-marketplace-content
git pull --ff-only origin arena/continue-marketplace-content
cd telegram-shop
pip install -r requirements.txt
cd ..
docker compose down || true
docker compose build --no-cache
docker compose up -d
```

## Вариант B — через готовый скрипт

```bash
cd /path/to/repo
git fetch origin
git checkout arena/continue-marketplace-content
git pull --ff-only origin arena/continue-marketplace-content
cd telegram-shop
pip install -r requirements.txt
cd ..
./deploy/deploy.sh
```

## Что проверить сразу после деплоя

Открыть в браузере:

- `/`
- `/warehouse/`
- `/download/android`
- `/download/android/rustore`
- `/privacy`
- `/api/releases/android`
- `/api/releases/android/qr.svg?mode=connect`

## Быстрый smoke-check APK 1.0.5

1. Установить `telegram-shop/apk/Sklad-1.0.5-release.apk`
2. Открыть `sklad://connect?...`
3. Проверить QR onboarding
4. Проверить web-сканер QR/штрих-кодов
5. Проверить native fallback scanner при проблемах WebView
6. Проверить экран обновлений APK

## SHA-256 текущих артефактов

```text
APK  c5991257914eca1e0277d79ef9ab6a7b0d41a7c555b3420d272025296eb9f940
AAB  68230e812b2ff81f9f449d64dbc134abdac24dbd17911da1da5686c0a483dd32
```

## Если что-то не работает

### QR не открывается
- проверить `WEBAPP_URL`
- проверить публичный HTTPS-домен
- убедиться, что установлен `qrcode`
- перезапустить backend после `pip install -r requirements.txt`

### Камера в APK не сканирует
- проверить разрешение `Camera`
- проверить, что открыт именно `/warehouse/`
- обновить Android System WebView
- убедиться, что срабатывает native fallback scanner

### RuStore-страница не готова
- заменить тестовый email поддержки
- вставить финальные скриншоты
- выбрать один финальный вариант поля «Что нового»
