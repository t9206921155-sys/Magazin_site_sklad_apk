# Блок 26 — Складской APK 1.1.0: нативные возможности обёртки

**Статус:** ✅ код готов и собран (APK/AAB built on CI); ⏳ доставка артефактов в репо — после переподключения GitHub
**Сессия:** 09.09.2026
**Зависит от:** блок 15 (безопасность — учтено), блоки 19–23 (endpoints склада)
**Связан с:** блок 25 (покупательское приложение — ОТЛОЖЕН по решению владельца)

---

## Цель

По запросу владельца: «делаем полноценное приложение склада, для клиентов пока
не надо! Без публикаций в Rustore». Прокачать нативную обёртку PWA склада
(`ru.telegramshop.sklad`) до **Sklad 1.1.0 (versionCode 8)**: убрать боль
удалённого использования APK с телефона. Покупательское приложение и сторы —
вне задачи.

## Сделано

### Нативные фичи (MainActivity.java, +220 строк)
1. **Сохранение файлов в «Загрузки»** — bridge `AndroidNative.saveFile(name, base64)`:
   - Android 10+: `MediaStore.Downloads` (без разрешений);
   - Android 6–9: `getExternalFilesDir(Download)` + манифест
     `WRITE_EXTERNAL_STORAGE` (maxSdk=28);
   - сохраняются: этикетки `labels.pdf`/`labels.prn`, ценники, PDF-отчёты,
     content-prompt JSON — всё, что раньше шло blob-скачиванием и в WebView
     не работало.
2. **Печать с телефона по Wi-Fi** — `AndroidNative.printRaw(host, port, base64)`:
   raw-сокет на принтер `:9100` (ZPL/EPL), таймаут 6/9 с, отдельный поток.
   Дублирует серверный прокси `/api/warehouse/print/network` для случая, когда
   VPS не виден из локальной сети склада.
3. **«Экран не гаснет»** — `keepAwake(true/false)` (FLAG_KEEP_SCREEN_ON),
   тумблер в настройках склада (виден только в APK), применение на старте.
4. **Вибро-фидбек** — `vibrateFeedback()` после успешного скана
   (нативный сканер и ТСД-сканы), `AndroidNative.vibrate(ms)`.
5. **Экран ошибки сети** — оверлей `error_wrap/error_text/btn_retry`
   (layout: FrameLayout поверх WebView), «Повторить подключение»,
   скрытие по успешной загрузке внутреннего URL. Вместо прежнего toast.
6. **Сканы от ТСД** — intent + deep link `sklad://scan?code=...&mode=...`
   (DataWedge и аналоги), вибро + `__nativeScanResult` в PWA.

### PWA склада (warehouse/app.js) — только при наличии `window.AndroidNative`
- `nativeBridge()`, `saveBlobNative()`, `blobToBase64()`;
- `downloadAuthed`, `downloadReport`, `exportPrompt` — в APK сохраняют
  нативно (в браузере поведение прежнее);
- кнопка «📱 Wi-Fi» в листе принтеров + `printWithPrinterLocal()`
  (`GET /api/warehouse/labels.prn` → raw-сокет с телефона);
- настройка «Экран не гаснет» в openSettings + применение на старте.

### Версии и сборка
- `build.gradle`: versionName 1.1.0, versionCode 8;
- `rebuild-apk.sh`: APP_VERSION/APP_CODE обновлены; **Gradle закреплён без
  env-подмены** (GRADLE_HOME раннера 9.x несовместим с AGP 8.2.2);
- манифест: + VIBRATE, + WRITE_EXTERNAL_STORAGE (maxSdk=28).

### CI (GitHub Actions через run-tests.sh → ci-build-apk.sh)
- Пайплайн `Tests` (уже существовавший) дополнен: после зелёных тестов
  собирает APK+AAB; защита от цикла — пропуск, если артефакты уже в репо;
- починен красный с 08.09 CI: в `.env.example` добавлены 5 ключей
  (TRUSTED_HOSTS, RATE_LIMIT_1C/API, WH_SESSION_TTL_DAYS, DISK_FREE_MIN_MB),
  в `requirements.txt` — Pillow, imageio-ffmpeg (версия 0.6.0!), jinja2;
- диагностика без доступа к логам: хвост лога прогона выгружается аннотациями
  (`CILOG[n]`, base64) и читается через check-runs API;
- **сборка на раннере успешна**: `Sklad-1.1.0-release.apk` 2.6M
  (versionCode=8, versionName=1.1.0, minSdk 23, target 34, label «Склад»),
  `Sklad-1.1.0-release.aab` 2.5M, подпись keystore — та же, что у 1.0.6
  (SHA-256 bf355bc6…), обновление без переустановки.

## Регрессия
- локально 368/368: labels 20 → hid 8 → stage5 23 → block06 33 → block09 47 →
  block13 33 → block14 32 → contracts 32 → block16 45 → block19 19 → block23 20 →
  pytest 16 → block15 40 (последним);
- `bash run-tests.sh` (тот же скрипт, что на CI) — зелёный;
- на раннере тесты тоже зелёные (видно в CILOG).
- PWA в браузере не изменена: все новые вызовы — под `if (nativeBridge())`.

## Что осталось (блокировано правами GitHub)

1. **⏳ Доставка артефактов в репо.** GITHUB_TOKEN прогона — read-only
   (`403 … denied to github-actions[bot]`), а push workflow-файлов от имени
   Arena-приложения запрещён (`workflows` permission). Готово к включению:
   - `telegram-shop/apk-build/ci/build-apk.workflow.yml` — workflow с
     `permissions: contents: write` (это поднимает права токена внутри прогона),
     коммитит APK/AAB в ветку + upload-artifact. **Нужно:** переподключить
     GitHub в Arena с правом workflows → файл переезжает в
     `.github/workflows/build-apk.yml` → `gh workflow run` → артефакты
     прилетают коммитом.
2. **⏳ Обновление релиза на сервере** — после п.1: `/apk/`, `/download/android`
   и `/api/releases/android` подхватят Sklad-1.1.0 автоматически (сканируют
   каталог), приложение увидит обновление через штатный update-check.
3. Тест на живом телефоне (вибро, печать по Wi-Fi, сохранение PDF) — после
   доставки APK.

## Решения

- Покупательское приложение (блок 25) — НЕ делаем, ТЗ остаётся отложенным.
- Публикации в RuStore/сторы — нет; распространение только своим сервером.
