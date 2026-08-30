# ✅ Merge-ready plan — ветка `arena/continue-marketplace-content`

Цель: безопасно довести ветку до состояния, когда её можно merge'ить в `main` без потери Android/RuStore/deploy-изменений.

## 1. Точка истины

Сейчас рабочая ветка для продолжения:

- branch: `arena/continue-marketplace-content`
- Android release: `1.0.6`
- package: `ru.telegramshop.sklad`
- ключевой функционал релиза: QR/deep link onboarding, `/download/android`, `/download/android/rustore`, `/privacy`, native fallback scanner для нестабильного WebView

## 2. Что должно быть проверено до merge

### Контент и карточка RuStore
- [ ] заполнен реальный email поддержки
- [ ] подтверждён moderator note
- [ ] выбрана финальная версия поля «Что нового»
- [ ] готовы 6 финальных скриншотов в одном стиле и одной ориентации
- [ ] проверены ссылки `/download/android`, `/download/android/rustore`, `/privacy`

### Android
- [ ] APK `telegram-shop/apk/Sklad-1.0.6-release.apk` устанавливается на реальном устройстве
- [ ] AAB `telegram-shop/aab/Sklad-1.0.6-release.aab` готов для RuStore
- [ ] deep link `sklad://connect?...` открывает приложение
- [ ] QR onboarding с `/api/releases/android/qr.svg` работает
- [ ] web-сканер читает QR/штрих-коды
- [ ] при сбое `BarcodeDetector` открывается native fallback scanner
- [ ] в настройках приложения работает проверка обновлений APK

### Backend / production
- [ ] production поднят с ветки `arena/continue-marketplace-content`
- [ ] установлены зависимости из `telegram-shop/requirements.txt`
- [ ] публичный `WEBAPP_URL` задан корректно
- [ ] открываются `/`, `/warehouse/`, `/download/android`, `/download/android/rustore`, `/privacy`
- [ ] `/api/releases/android` возвращает актуальные данные по `1.0.6`

## 3. Рекомендуемый порядок действий

1. Обновить production из ветки `arena/continue-marketplace-content`
2. Пройти smoke-check сайта и Android-страниц
3. Проверить APK `1.0.6` на телефоне
4. Подготовить/залить финальные RuStore-ассеты
5. Зафиксировать SHA-256 и release note во внутренней заметке
6. Только после этого делать merge в `main`

## 4. Команды проверки перед merge

### Локально

```bash
cd /path/to/repo
git fetch origin
git checkout arena/continue-marketplace-content
git pull --ff-only origin arena/continue-marketplace-content
git status
```

### Production update

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

## 5. Merge-ready критерии

Считать ветку готовой к merge, если одновременно выполнено всё ниже:

- `origin/arena/continue-marketplace-content` содержит финальный commit релиза
- production уже работает на этом commit без регрессий
- APK `1.0.6` проверен на реальном Android-устройстве
- RuStore-карточка заполнена актуальными текстами и реальными контактами
- финальные скриншоты сделаны с текущего интерфейса
- подтверждено поведение native fallback scanner

## 6. Когда выполнять merge

Merge в `main` имеет смысл делать только после двух подтверждений:

1. **техническое** — production и APK smoke-check пройдены;
2. **контентное** — RuStore-материалы и скриншоты финализированы.

## 7. Команды merge после подтверждения

```bash
cd /path/to/repo
git fetch origin
git checkout main
git pull --ff-only origin main
git merge --no-ff origin/arena/continue-marketplace-content -m "Merge branch 'arena/continue-marketplace-content'"
git push origin main
```

Если перед merge в feature-ветке появились новые правки — сначала ещё раз обновить и перепроверить ветку, и только потом сливать в `main`.
