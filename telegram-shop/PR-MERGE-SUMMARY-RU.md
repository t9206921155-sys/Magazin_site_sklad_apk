# PR / Merge summary — `arena/continue-marketplace-content`

## Что вошло в ветку

Ветка `arena/continue-marketplace-content` доводит Android-направление проекта до состояния, пригодного для production rollout и подготовки публикации в RuStore.

### Основные изменения
- добавлен Android-лендинг `/download/android`
- добавлена RuStore-страница `/download/android/rustore`
- добавлена публичная privacy page `/privacy`
- добавлены JSON-метаданные релиза `/api/releases/android`
- добавлена генерация SVG QR для onboarding `/api/releases/android/qr.svg`
- подготовлены deploy- и RuStore-чеклисты
- Android wrapper обновлён до `1.0.5 / versionCode 6`
- добавлен native fallback scanner bridge для QR/штрих-кодов, если `BarcodeDetector` в WebView нестабилен

## Зачем это изменение

Цель — сделать Android APK не просто внутренней сборкой, а управляемым релизным каналом:
- сотрудник может установить APK и подключиться к складу по deep link или QR
- владелец проекта получает готовый пакет материалов для RuStore
- приложение устойчивее работает на Android-устройствах за счёт native fallback scanner
- production rollout и последующий merge в `main` теперь можно проводить по явному checklist

## Пользовательская ценность

- быстрее onboarding сотрудников склада
- меньше сбоев при сканировании QR/штрих-кодов в WebView
- готовая страница публикации для RuStore
- отдельные APK/AAB-артефакты для ручной установки и стора

## Технические детали

### Android
- package: `ru.telegramshop.sklad`
- release: `1.0.5`
- `versionCode`: `6`
- APK: `telegram-shop/apk/Sklad-1.0.5-release.apk`
- AAB: `telegram-shop/aab/Sklad-1.0.5-release.aab`

### Web / backend
- `/download/android`
- `/download/android/rustore`
- `/privacy`
- `/api/releases/android`
- `/api/releases/android/qr.svg`

### Документация
- `telegram-shop/DEPLOY-CHECKLIST.md`
- `telegram-shop/PROD-DEPLOY-QUICKSTART.md`
- `telegram-shop/MERGE-READY-PLAN.md`
- `telegram-shop/MERGE-COMMAND-BLOCK.md`
- `telegram-shop/RUSTORE-CARD-CHECKLIST.md`

## Проверки

Пройдено:
- `python3 -m py_compile api.py seo.py store.py`
- Jinja templates load check
- `node --check warehouse/app.js`
- Android release build success

Рекомендуется дополнительно перед merge:
- пройти production smoke-check
- проверить APK на реальном Android-устройстве
- подтвердить deep link, QR onboarding и native fallback scanner
- заменить тестовый support email на боевой
- подготовить финальные скриншоты RuStore

## Риски и что проверить ревьюеру

- что публичный `WEBAPP_URL` настроен корректно
- что `/privacy` открывается без авторизации
- что `/api/releases/android` отдаёт актуальную версию `1.0.5`
- что Android WebView не ломает scanner flow и при сбое открывается native fallback
- что в RuStore не остались тестовые контакты

## Рекомендуемый порядок после merge

1. Обновить production
2. Пройти smoke-check страниц и release endpoints
3. Проверить APK `1.0.5` на телефоне
4. Завершить публикационный пакет RuStore
5. После этого считать релиз полностью завершённым
