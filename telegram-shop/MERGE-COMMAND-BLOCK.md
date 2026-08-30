# 🔀 Merge command block — точные команды

Ниже готовые команды для текущего workflow проекта.

## 1. Обновить production с feature-ветки

Замените только путь `/path/to/repo` и домен `https://example.com`.

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
./telegram-shop/scripts/post_deploy_smoke_check.sh https://example.com
```

## 2. Проверить merge-ready состояние

```bash
cd /path/to/repo
git fetch origin
git checkout arena/continue-marketplace-content
git pull --ff-only origin arena/continue-marketplace-content
git status
./telegram-shop/scripts/post_deploy_smoke_check.sh https://example.com
```

Дополнительно вручную проверить на Android-устройстве:
- установку `telegram-shop/apk/Sklad-1.0.5-release.apk`
- deep link `sklad://connect?...`
- QR onboarding
- web-сканер и native fallback scanner
- экран проверки обновлений APK

## 3. Merge в `main` после smoke-check

```bash
cd /path/to/repo
git fetch origin
git checkout main
git pull --ff-only origin main
git merge --no-ff origin/arena/continue-marketplace-content -m "Merge branch 'arena/continue-marketplace-content'"
git push origin main
```

## 4. Если хотите отдельно зафиксировать production на `main`

После merge можно обновить сервер ещё раз уже из `main`:

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
./telegram-shop/scripts/post_deploy_smoke_check.sh https://example.com
```

## 5. Текущий ожидаемый результат

- ветка релиза: `arena/continue-marketplace-content`
- APK: `telegram-shop/apk/Sklad-1.0.5-release.apk`
- AAB: `telegram-shop/aab/Sklad-1.0.5-release.aab`
- package: `ru.telegramshop.sklad`
- public pages: `/download/android`, `/download/android/rustore`, `/privacy`
