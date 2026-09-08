# Staging и production validation runbook

## Автоматическая часть

```bash
python3 -m pytest -q tests
python3 -m py_compile telegram-shop/api.py telegram-shop/store.py marketing_adapters.py
```

Перед deploy проверить права, diff и секреты:

```bash
git diff --summary
git diff --cached --summary | grep -i 'mode change' || true
python3 telegram-shop/scripts/check-env-keys.py
```

## Переменные окружения

Заполнять только на VPS/secret manager, не в Git:

```text
CONTENT_CALLBACK_SECRET=
TELEGRAM_ADAPTER_TOKEN=
TELEGRAM_ADAPTER_ACCOUNT_ID=
VK_ADAPTER_TOKEN=
VK_ADAPTER_ACCOUNT_ID=
AVITO_ADAPTER_TOKEN=
AVITO_ADAPTER_ACCOUNT_ID=
META_ADAPTER_TOKEN=
META_ADAPTER_ACCOUNT_ID=
TIKTOK_ADAPTER_TOKEN=
TIKTOK_ADAPTER_ACCOUNT_ID=
WILDBERRIES_ADAPTER_TOKEN=
WILDBERRIES_ADAPTER_ACCOUNT_ID=
```

## Ручная staging-проверка

1. Включить HTTPS и проверить сертификат.
2. Проверить миграцию новых таблиц на копии staging базы.
3. Создать кампанию с двумя каналами.
4. Подготовить публикации, approve и выполнить dry-run.
5. Проверить callback video job с корректной HMAC-подписью.
6. Проверить неправильную подпись и повторный callback.
7. Для каждого provider выполнить только одну тестовую публикацию.
8. Зафиксировать внешний ID, ответ API и ошибку/успех без секретов.
9. Проверить backup и restore staging базы.
10. Проверить rollback предыдущего release.

## Production gate

Production publish разрешается только после ручного подтверждения API scopes, rate limits, account permissions, rollback и backup/restore. Screenshots делать только в staging/production, без токенов и персональных данных.

## Preflight

Перед каждым deploy запускать:

```bash
deploy/preflight-validation.sh
```

Скрипт останавливается при ошибке syntax/tests/mode changes или если adapter boundary больше не dry-run gated.

## Rollback preflight

Проверить наличие backup без выполнения restore:

```bash
deploy/rollback-preflight.sh /path/to/backup.sqlite
```

Скрипт только проверяет файл и расширение. Restore в sandbox или production автоматически не выполняется.

## HTTPS preflight

На staging/production проверить HTTPS и HSTS:

```bash
deploy/https-preflight.sh https://example.com
```

В sandbox этот шаг не выполняется против production URL.

## Environment preflight

Перед deploy проверить environment без вывода secret values:

```bash
deploy/env-preflight.sh
deploy/secret-scan.sh
```

В demo режиме отсутствие credentials допустимо, потому что реальные adapters отключены.
