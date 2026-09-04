# 🧭 SESSION-PLAYBOOK — регламент работы в песочнице

> Как поднять окружение, не упереться в лимит размера и корректно
> синхронизироваться. Все команды ниже проверены на практике.

---

## Проблема, ради которой написан этот файл

| Что | Размер |
|---|---|
| Полный клон (`git clone`) | **106 МБ** |
| из них `.git` с историей | 74 МБ |
| Лимит снапшота песочницы | ~128 МБ |

Полный клон почти упирается в лимит: после установки зависимостей и запуска
сервера места не остаётся, а снапшот может не сохраниться.

**Решение — лёгкий клон на 7 МБ** (в 15 раз меньше), код при этом весь на месте.

---

## Шаг 1. Клонирование (обязательно так)

```bash
cd /home/user
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git repo
cd repo
git sparse-checkout set --no-cone '/*' \
  '!telegram-shop/screenshots' '!telegram-shop/apk' '!telegram-shop/aab'
```

Что даёт каждый флаг:

| Флаг | Эффект |
|---|---|
| `--depth 1` | только последний коммит, без истории (−46 МБ) |
| `--filter=blob:none` | файлы качаются по требованию |
| `--sparse` + `sparse-checkout` | не выгружать скрины (22 МБ), APK и AAB (5 МБ) |

Проверка: `du -sh .` должно показать **~7 МБ**.

> Если понадобятся скриншоты или APK:
> `git sparse-checkout add telegram-shop/screenshots`

---

## Шаг 2. Зависимости

Пакеты **не переживают** перезапуск сессии — ставить заново каждый раз:

```bash
cd telegram-shop
pip install -q -r requirements.txt
python3 -c "import uvicorn,fastapi,reportlab,qrcode; print('deps ok')"
```

---

## Шаг 3. Запуск

```bash
cp .env.example .env          # если .env ещё нет
sed -i 's|^BOT_TOKEN=.*|BOT_TOKEN=|' .env   # без токена бот отключён, сайт работает
python3 bot.py                # только через start_process, не через bash
```

Проверка живости:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/
```

Вход в склад: `admin` / `admin123`.

```bash
TOK=$(curl -s -X POST http://127.0.0.1:8000/api/warehouse/login \
  -H 'Content-Type: application/json' \
  -d '{"login":"admin","password":"admin123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
```

---

## Шаг 4. Работа по блоку

1. Открыть `ROADMAP.md`, найти первый блок со статусом ⏳.
2. Открыть его план `blocks/BLOCK-XX-*.md`.
3. Выполнить задачи из раздела «Задачи».
4. Прогнать критерии из раздела «Критерии приёмки».
5. Заполнить в файле блока раздел «Отчёт».
6. Обновить строку блока в таблице `ROADMAP.md` (⏳ → ✅).

**Один блок = одна сессия.** Не начинать следующий, пока текущий не закрыт.

---

## Шаг 5. Регрессия перед коммитом

```bash
cd telegram-shop
python3 tests-labels.py       # ожидается 20 passed
node tests-hid-scanner.js     # ожидается  8 passed
python3 tests-stage5.py       # ожидается 23 passed (нужен запущенный сервер)
```

Плюс страницы:

```bash
for u in / /catalog /shop /app /warehouse/ /sitemap.xml; do
  printf "%-14s %s\n" "$u" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000$u)"
done
```

---

## Шаг 6. Синхронизация

### ⚠️ Проверить права перед коммитом

Флаги `chmod +x` регулярно слетают и попадают в коммит мусором:

```bash
git add -A
git diff --cached --summary | grep -i "mode change"   # должно быть пусто
```

Если нашлись — вернуть:

```bash
git update-index --chmod=+x deploy/deploy.sh mobile/build-apk.sh \
  telegram-shop/apk-build/rebuild-apk.sh \
  telegram-shop/scripts/backup_sqlite_to_s3.py \
  telegram-shop/scripts/merge_feature_to_main.sh \
  telegram-shop/scripts/post_deploy_smoke_check.sh \
  telegram-shop/scripts/release_status.sh
```

### Коммит и push

```bash
git -c user.email=agent@arena.local -c user.name="Arena Agent" \
  commit -m "Block NN: краткая суть

Что изменено и почему. Какие баги найдены.
Tests: X/X."

git fetch origin main
git merge-base --is-ancestor FETCH_HEAD HEAD && echo "fast-forward OK"

git -c credential.helper= \
  -c http.extraheader="AUTHORIZATION: basic $(printf 'x-access-token:ТОКЕН' | base64 -w0)" \
  push origin HEAD:main
```

> Токен передавать **только** через `http.extraheader` — так он не попадёт
> в `remote.origin.url` и не сохранится в `.git/config`.
> В выводе маскировать: `| sed 's/ghp_[A-Za-z0-9]*/<скрыт>/g'`.

### Проверить, что долетело

```bash
cd /tmp && rm -rf verify
git clone -q --depth 1 https://github.com/t9206921155-sys/Magazin_site_sklad_apk.git verify
cd verify && git log --oneline -3
cd /tmp && rm -rf verify
```

---

## Если push невозможен (нет токена)

Отдать пользователю бандл — он весит килобайты:

```bash
git bundle create /home/user/sync.bundle origin/main..HEAD
```

Применяется у пользователя так:

```bash
git fetch /путь/к/sync.bundle && git merge --ff-only FETCH_HEAD && git push origin main
```

---

## Грабли, на которые уже наступали

| Грабли | Как обойти |
|---|---|
| Полный клон 106 МБ забивает песочницу | sparse-клон, Шаг 1 |
| Пакеты pip исчезают между сессиями | ставить заново, Шаг 2 |
| Сервер умирает между ходами | перезапускать через `start_process` |
| `remote` пропадает после сброса сессии | `git remote add origin ...` |
| `git add -A` снимает `chmod +x` | проверка из Шага 6 |
| `window.open` не шлёт заголовки | скачивать через `fetch` + blob |
| Патч с бинарниками раздувается до 28 МБ | использовать bundle |
| `.zip` не грузится в чат | только текстовые форматы, либо публичный репозиторий |
