# Блок 29 — Финальная доводка: гигиена, staging-автоматы, бэкенд RN

**Статус:** ✅ выполнен 12.09.2026
**Сессия:** 12.09.2026
**Зависит от:** блоки 25, 28 — выполнены
**Оценка:** одна-две сессии

---

## Цель

Довести проект до ума: убрать накопившиеся шероховатости, автоматизировать
всё автоматизируемое из ручных блоков 17/18, реализовать серверную часть
ТЗ покупательского приложения (§6.2 — без внешних зависимостей).

## Задачи

### Ч1. Гигиена версий и скриптов
- [x] Фолбэк 1.0.6→1.1.0 в `api.py`; параметризовать `release_status.sh` (+ Shop)
- [x] 1.0.6→1.1.0 в операционных доках (исторические не трогать)
- [x] `mobile/build-apk.sh`: заглушка → редирект; `mobile/README.md`; честный `package.json`
- [x] `install.sh` → обёртка над `setup.sh`
- [x] `.env.example`: пустые BOT_TOKEN/ADMIN_IDS вместо фейка
- [x] `--help` и защита от флагов в обоих `build-apk.sh`

### Ч2. Lock-файл и staging-автоматизация
- [x] `telegram-shop/requirements-lock.txt` из чистого venv
- [x] `deploy/backup-drill.sh` (авто-часть блока 18) + тесты
- [x] `deploy/staging-report.sh` (авто-часть блока 17) + тесты
- [x] Документация: BLOCK-18 примечание, SETUP-AUTO.md раздел приёмки

### Ч3. Бэкенд покупательского приложения (ТЗ §6.2)
- [x] `GET /api/product/{id}` — карточка одним запросом
- [x] `POST /api/mobile/register` + таблица `mobile_devices`
- [x] FCM-хуки (dry-run gated, как остальные провайдеры) + диагностика
- [x] `GET /api/app/version?platform=` (обратная совместимость)
- [x] `FCM_CREDENTIALS_JSON` в config + `.env.example` + `setup-env.sh`
- [x] `tests-block29.py` + регистрация в `run-tests.sh` и ROADMAP
- [x] ANDROID-APP-TZ §6.2 и BLOCK-25: пометить серверную часть ✅

### Ч4. Финал
- [x] PR ветки в `main`
- [x] ROADMAP: блок 29 ✅, счётчики
- [x] Финальная синхронизация (CI-лог подтянут)

## Критерии приёмки

- [x] `pytest tests/` зелёный (45+ тестов)
- [x] Полный `run-tests.sh` зелёный (включая новый сюит)
- [x] `backup-drill.sh` проходит на синтетической и реальной БД
- [x] Ни одного `1.0.6` вне исторических документов и `blocks/`
- [x] PR открыт, CI на ветке зелёный

## Отчёт (12.09.2026)

### Ч1. Гигиена
- `api.py`: фолбэки версий → 1.1.0; `release_status.sh` параметризован (+ Shop APK).
- 51 замена 1.0.6→1.1.0 в операционных доках (+ RUSTORE операционные строки);
  исторические handoff/summary/релизноуты не тронуты.
- `mobile/build-apk.sh`: заглушка → редирект; `mobile/README.md`; честный `package.json`.
- `install.sh` → обёртка над `setup.sh`; `.env.example` без фейкового токена.
- `--help`/защита от флагов в обоих `build-apk.sh` (раньше `--help` качал JDK).

### Ч2. Lock и staging-автоматы
- `requirements-lock.txt` (61 пакет, чистый venv).
- `deploy/backup-drill.sh` + `deploy/staging-report.sh` + 10 pytest.
- Исправлен путь в ТЗ: `POST /api/order` (единственное число, как в коде).

### Ч3. Бэкенд RN (ТЗ §6.2)
- `GET /api/product/{id}` (секреты склада вычищены), `POST /api/mobile/register`,
  `DELETE /api/mobile/devices/{guest_id}`, `GET /api/mobile/status`,
  `?platform=` у `/api/app/version`; таблица `mobile_devices`.
- FCM-хуки: статусы заказов (админка, бот, 1С, 3 вебхука), ответы в чате/офферах.
  Всё dry-run gated (`FCM_DRY_RUN=1`); боевой транспорт — staging Фаза 5.
- `FCM_CREDENTIALS_JSON`/`FCM_DRY_RUN` в config/`.env.example`/`setup-env.sh` (20 ключей).
- `tests-block29.py` 30/30; сюиты 13/16/19/23/15 возвращены в `run-tests.sh`
  (полная регрессия ~545 проверок одной командой, CI).

### Найденные по ходу баги
- Параллельные `edit_file` в один файл затирают друг друга — часть правок
  блока 28 (ROADMAP ×3, `release_status.sh`, `import config`, SCHEMA-таблица)
  была потеряна и восстановлена; правило: один файл — один вызов за раз.
- `run-tests.sh` не гонял сюиты 13/16/19/23/15 (дрейф от ROADMAP) — возвращены.
- ТЗ §6.1 врало путь `POST /api/orders` (реально `/api/order`) — исправлено.

### Регрессия 12.09.2026
Полный `run-tests.sh`: EXIT=0 — health 2, storage-contracts 32, labels 20,
hid 8, stage5 23, block06 33, block09 47, block13 33, block14 32, block16 45,
block19 19, block23 20, block25 29, block27 86, block29 30, pytest 45,
block15 40 (последним). `setup.sh --check`-эквивалент покрыт CI.

