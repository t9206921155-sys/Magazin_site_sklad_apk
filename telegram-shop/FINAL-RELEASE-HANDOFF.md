# 📦 Final release handoff — Android «Склад» 1.0.5

Итоговый handoff-пакет по ветке `arena/continue-marketplace-content`.

## 1. Текущее состояние

- рабочая ветка: `arena/continue-marketplace-content`
- целевой Android-релиз: `1.0.5`
- package: `ru.telegramshop.sklad`
- основной Android commit chain:
  - `d33d703` — deploy checklist + scanner inside APK
  - `fa11746` — native fallback scanner + финализация RuStore-материалов
  - `0db9444` — changelog + merge checklist
  - `f927686` — merge-ready plan + prod deploy quickstart
  - `7e62897` — merge-команды + smoke-check + PR summary
  - `88baf5f` — automation deploy/merge workflow

## 2. Готовые артефакты

- APK: `telegram-shop/apk/Sklad-1.0.5-release.apk`
- AAB: `telegram-shop/aab/Sklad-1.0.5-release.aab`

SHA-256:

```text
APK  c5991257914eca1e0277d79ef9ab6a7b0d41a7c555b3420d272025296eb9f940
AAB  68230e812b2ff81f9f449d64dbc134abdac24dbd17911da1da5686c0a483dd32
```

## 3. Что уже доведено до готового состояния

### Android
- deep link onboarding: `sklad://setup` / `sklad://connect`
- QR onboarding endpoint: `/api/releases/android/qr.svg`
- release metadata endpoint: `/api/releases/android`
- Android wrapper: `1.0.5 / versionCode 6`
- native fallback scanner bridge для случаев, когда `BarcodeDetector` в WebView нестабилен

### Контент / RuStore
- готовый moderator note
- финальный набор из 6 подписей для скриншотов
- несколько вариантов поля «Что нового»
- отдельная RuStore-страница `/download/android/rustore`
- privacy page `/privacy`

### Delivery / ops
- production deploy quickstart
- merge-ready plan
- точный merge command block
- post-deploy smoke-check script
- merge helper script
- PR / merge summary на русском

## 4. Основные файлы handoff-пакета

- `telegram-shop/RUSTORE-CARD-CHECKLIST.md`
- `telegram-shop/DEPLOY-CHECKLIST.md`
- `telegram-shop/PROD-DEPLOY-QUICKSTART.md`
- `telegram-shop/MERGE-READY-PLAN.md`
- `telegram-shop/MERGE-COMMAND-BLOCK.md`
- `telegram-shop/PR-MERGE-SUMMARY-RU.md`
- `telegram-shop/scripts/post_deploy_smoke_check.sh`
- `telegram-shop/scripts/merge_feature_to_main.sh`

## 5. Самые полезные команды

### Production deploy

```bash
cd /path/to/repo
./deploy/deploy.sh --domain https://example.com --expected-version 1.0.5
```

### Post-deploy smoke-check

```bash
cd /path/to/repo
./telegram-shop/scripts/post_deploy_smoke_check.sh https://example.com 1.0.5
```

### Быстрая сводка статуса релиза

```bash
cd /path/to/repo
./telegram-shop/scripts/release_status.sh
```

### Merge в main после проверки

```bash
cd /path/to/repo
./telegram-shop/scripts/merge_feature_to_main.sh --push
```

## 6. Что ещё обязательно проверить руками

- APK `telegram-shop/apk/Sklad-1.0.5-release.apk` на реальном Android-устройстве
- deep link `sklad://connect?...`
- QR onboarding
- web-сканер QR/штрих-кодов
- переход в native fallback scanner при проблемах WebView
- экран проверки обновлений APK
- реальные support contacts в RuStore
- финальные 6 скриншотов

## 7. Когда можно считать релиз завершённым

Релиз можно считать полностью закрытым, когда одновременно выполнено всё ниже:

- production поднят с ветки `arena/continue-marketplace-content`
- smoke-check прошёл успешно
- Android APK проверен на устройстве
- RuStore-карточка заполнена актуальными материалами
- принято решение: либо публиковать в RuStore, либо делать merge в `main`
