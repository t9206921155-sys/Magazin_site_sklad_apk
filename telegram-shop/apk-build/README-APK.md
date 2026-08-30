# 📦 Android «Склад» — APK и AAB

**Этап 1 плана склада (WAREHOUSE-PLAN.md) — ВЫПОЛНЕН 26.08.2026.**

Android-приложение «Склад» — это WebView-обёртка PWA `/warehouse/` в духе PWABuilder.
Выбран вариант **без TWA** (TWA/Trusted Web Activity требует публикации в Google Play и
файла assetlinks.json на HTTPS-домене; для ручной раздачи APK он не подходит).

## Что умеет приложение

| Возможность | Как работает |
|---|---|
| Полный интерфейс склада | WebView загружает `/warehouse/` с вашего сервера |
| Ввод адреса сервера | При первом запуске — нативный экран настройки (не нужно пересобирать APK под каждый сервер) |
| Смена сервера | Долгое нажатие на экран склада → экран настроек |
| Быстрая настройка по ссылке | deep link: `sklad://setup?url=...` или `sklad://connect?url=...` |
| QR-подключение | сервер может отдать SVG QR-код для deep link: `/api/releases/android/qr.svg` |
| Фото товаров с камеры | `input type=file` пробрасывается в системный выбор файлов/камеры |
| Сканер QR / штрих-кодов | WebView-сканер + нативный Android fallback, если BarcodeDetector нестабилен |
| Авторизация сохраняется | Cookies + DOM storage включены |
| Внешние ссылки | t.me, оплата и т.п. открываются в браузере/приложениях |
| Локальная сеть | Разрешён http (usesCleartextTraffic) — сервер в Wi-Fi сети склада без HTTPS |

## Готовые артефакты

```
telegram-shop/apk/Sklad-1.0.5-release.apk
telegram-shop/aab/Sklad-1.0.5-release.aab
```

| Параметр | Значение |
|---|---|
| Имя пакета | `ru.telegramshop.sklad` |
| Версия | 1.0.5 (versionCode 6) |
| minSdk | Android 6.0 (API 23) |
| targetSdk | Android 14 (API 34) |
| Подпись | release-ключ `keystore/telegramshop.keystore` (используется и для APK, и для AAB) |

## Установка на телефон (раздача вручную)

1. Переслать APK себе в Telegram (Избранное) → открыть → «Сохранить в загрузки».
2. Открыть файл → Android спросит разрешение «Устанавливать из этого источника» → разрешить.
3. Первый запуск: ввести адрес сервера, например `https://myshop.ru/warehouse/`
   (если путь не указан — `/warehouse/` добавится автоматически).
4. После установки можно открыть ссылку вида `sklad://connect?url=https://myshop.ru/warehouse/` или отсканировать QR-код со страницы `/download/android` — приложение само подставит сервер.
5. На экране настроек (долгое нажатие внутри приложения) доступна проверка новой версии APK.
6. Встроенный сканер в `/warehouse/` сначала пробует WebView-камеру, а при проблемах автоматически открывает нативный Android fallback.
7. Войти под учёткой склада (например, demo-сотрудник `ivan` / `ivan123`).

## Пересборка

```bash
cd apk-build
./rebuild-apk.sh [URL_ПО_УМОЛЧАНИЮ]
# пример: ./rebuild-apk.sh https://myshop.ru/warehouse/
```

Скрипт сам ставит JDK 17, Android SDK (platform 34, build-tools 34.0.0), Gradle 8.2.1
в пользовательский cache (`~/.cache`), генерирует release-ключ и иконки, собирает и проверяет подпись.
Результат:
- `telegram-shop/apk/Sklad-1.0.5-release.apk`
- `telegram-shop/aab/Sklad-1.0.5-release.aab`

Текущая версия: `android/app/build.gradle` → `versionCode 6` / `versionName "1.0.5"`.

## Публикация в RuStore

Для ручной установки используйте APK, для публикации в RuStore / Google Play — AAB.
Скрипт `./rebuild-apk.sh` собирает **оба артефакта сразу**.
Дополнительно появились:
- страница материалов для публикации: `/download/android/rustore`
- политика конфиденциальности: `/privacy`
- QR и JSON-метаданные релиза: `/api/releases/android`, `/api/releases/android/qr.svg`
- deploy-checklist: `DEPLOY-CHECKLIST.md`
- чек-лист карточки RuStore: `RUSTORE-CARD-CHECKLIST.md`

Консоль RuStore: developer.rustore.ru. TWA не требуется.

## Дальше по плану

- **Этап 2**: push-уведомления (нужен HTTPS-домен), экспорт, массовое редактирование.
- **Этап 5**: офлайн-режим с очередью операций (аналог Isar) — WebView-кэш + очередь в localStorage.
- Bluetooth-печать на реальном XP-365 — тестирование на устройстве (форматы TSPL-совместимые готовы в /labels.prn).
