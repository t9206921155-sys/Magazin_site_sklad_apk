# 🚀 PROD deploy quickstart — copy/paste

Короткая инструкция для выкладки актуальной ветки `main` в production.

## Вариант A — Docker deploy из корня репозитория

```bash
cd /path/to/repo
git fetch origin
git checkout main
git pull --ff-only origin main
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
./deploy/deploy.sh --domain https://example.com --expected-version 1.0.6
```

Полезные флаги:
- `--branch main`
- `--expected-version 1.0.6`
- `--skip-smoke`
- `--skip-pip`
- `--cache`

## Что проверить сразу после деплоя

Открыть в браузере:

- `/`
- `/warehouse/`
- `/download/android`
- `/download/android/rustore`
- `/privacy`
- `/api/releases/android`
- `/api/releases/android/qr.svg?mode=connect`

## Быстрый smoke-check APK 1.0.6

1. Установить `telegram-shop/apk/Sklad-1.0.6-release.apk`
2. Открыть `sklad://connect?...`
3. Проверить QR onboarding
4. Проверить web-сканер QR/штрих-кодов
5. Проверить native fallback scanner при проблемах WebView
6. Проверить экран обновлений APK

Сводка релиза: `FINAL-RELEASE-HANDOFF.md`

## SHA-256 текущих артефактов

```text
APK  fbbd2b10bf03c5f37aa2fea7ed8d32869141832e296e1f5f23005f09436878df
AAB  0411fad61826701a31e32cd76af90ed9c38906b380a1feb566aaa908e6d2aef0
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
