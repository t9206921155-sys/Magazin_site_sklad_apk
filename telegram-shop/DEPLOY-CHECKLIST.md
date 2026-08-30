# ✅ Deploy checklist — Telegram Shop + Android «Склад»

Короткий production-checklist для выкладки ветки `arena/continue-marketplace-content`.

## 1. Обновить код на сервере

```bash
git fetch origin
git checkout arena/continue-marketplace-content
git pull --ff-only origin arena/continue-marketplace-content
```

## 2. Проверить Python-зависимости

```bash
cd telegram-shop
pip install -r requirements.txt
```

Важно: в этой ветке добавлен пакет `qrcode`, он нужен для SVG-QR по пути:
- `/api/releases/android/qr.svg`

## 3. Проверить обязательные env / домен

Перед выкладкой убедиться, что настроены:
- `WEBAPP_URL` — публичный HTTPS-домен проекта
- `BOT_TOKEN`, `ADMIN_IDS`, `ADMIN_PASSWORD`
- настройки платежей / облака / push при необходимости

Для Android и публикации важно, чтобы снаружи открывались:
- `/download/android`
- `/download/android/rustore`
- `/privacy`
- `/api/releases/android`
- `/api/releases/android/qr.svg`

## 4. Проверить release-артефакты Android

В репозитории должны лежать актуальные файлы:
- `apk/Sklad-1.0.6-release.apk`
- `aab/Sklad-1.0.6-release.aab`

Проверка:

```bash
sha256sum apk/Sklad-1.0.6-release.apk aab/Sklad-1.0.6-release.aab
```

## 5. Перезапустить приложение

Если используется docker compose:

```bash
cd /path/to/repo
docker compose down || true
docker compose build --no-cache
docker compose up -d
```

Если без Docker — перезапустить uvicorn/systemd/supervisor-процесс вручную.

## 6. Smoke-check после деплоя

Открыть и проверить:
- главную страницу `/`
- склад `/warehouse/`
- Android-лендинг `/download/android`
- RuStore-страницу `/download/android/rustore`
- privacy page `/privacy`
- JSON релизов `/api/releases/android`
- SVG QR `/api/releases/android/qr.svg?mode=connect`

## 7. Android smoke-check на телефоне

Проверить реальным устройством:
1. установка `Sklad-1.0.6-release.apk`
2. открытие `sklad://connect?...`
3. сканирование QR с `/download/android`
4. запуск сканера в `/warehouse/` внутри APK
5. системный запрос разрешения камеры
6. чтение штрих-кода / QR
7. при проблемах WebView — автопереход в нативный Android fallback
8. экран обновлений APK в настройках

## 8. Перед публикацией в RuStore

Проверить ещё раз:
- загружается именно `aab/Sklad-1.0.6-release.aab`
- доступна страница `/privacy`
- заполнены реальные контакты поддержки
- сделаны финальные скриншоты актуального интерфейса
- package name совпадает: `ru.telegramshop.sklad`

## 9. Если QR не работает

Почти всегда причина одна из трёх:
- не установлен пакет `qrcode`
- сервер не был перезапущен после обновления зависимостей
- `WEBAPP_URL` или публичный домен настроен некорректно

## 10. Если камера в APK не сканирует

Проверить:
- Android выдал разрешение `Camera`
- WebView обновлён на устройстве
- открывается именно `/warehouse/`
- при ошибке BarcodeDetector срабатывает нативный fallback-сканер
- страница работает по HTTPS либо разрешён нужный сценарий в локальной сети
- в приложении установлена версия `1.0.6`

## 11. Следующий шаг после этого релиза

Минимальный порядок действий:
1. обновить production из ветки `arena/continue-marketplace-content`
2. пройти smoke-check сайта, Android-лендинга и APK `1.0.6`
3. отдельно проверить deep link, QR onboarding и сценарий native fallback scanner
4. зафиксировать SHA-256 APK/AAB в заметке релиза или внутреннем журнале
5. только после успешной проверки готовить merge в `main`

## 12. Merge-ready критерии

Считать ветку готовой к merge, если одновременно выполнено всё ниже:
- `origin/arena/continue-marketplace-content` содержит актуальный commit релиза
- страницы `/download/android`, `/download/android/rustore` и `/privacy` открываются с production-домена
- APK `1.0.6` устанавливается и подключается к складу по `sklad://connect?...`
- web-сканер работает, а при сбое корректно открывается native fallback scanner
- RuStore-карточка заполнена актуальными текстами, скриншотами и рабочими контактами поддержки
