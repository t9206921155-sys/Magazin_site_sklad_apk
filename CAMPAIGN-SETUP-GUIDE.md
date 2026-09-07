# Campaign Manager: настройка и проверка

## 1. Локальный режим без credentials

1. Запустить API обычным способом проекта.
2. Открыть `/crm/` и войти складским пользователем.
3. Создать кампанию, например:

```json
{"name":"Летняя распродажа","channels":["telegram","vk","avito"],"utm":{"source":"social","medium":"campaign","campaign":"summer-sale"}}
```

4. Для выбранного канала нажать «Подготовить».
5. Публикация создаётся как `draft`.
6. До approve package и dry-run должны возвращать ошибку 409.
7. Нажать «Одобрить последнюю».
8. Проверить:

```text
GET /api/marketing/publications/{id}/package
POST /api/marketing/publications/{id}/dry-run
```

Dry-run не обращается к соцсети и возвращает `mode: stub`.

## 2. Внешний video pipeline

```text
POST /api/content/jobs
→ queued
→ внешний сервис получает prompt
→ POST /api/content/jobs/{id}/result
→ review
→ approve/reject
```

Секреты внешнего сервиса не хранить в Git, README или query-параметрах. До подключения callback можно импортировать `result_url` вручную.

## 3. Подключение официального provider

Для каждой площадки отдельно подтвердить:

- официальный API и актуальную документацию;
- тип credentials и scopes;
- account/page/seller permissions;
- rate limits;
- sandbox или тестовый аккаунт;
- формат ошибок и повторных запросов.

После этого реализовать adapter, заменить dry-run на staging transport и оставить ручной approve обязательным.

## 4. Wildberries

WB остаётся отключённым до завершения account/API audit. Не использовать scraping, browser automation или неофициальные endpoints. Проверять состояние через:

```text
GET /api/marketing/wildberries/audit
```

## 5. Перед production

- выполнить manual checklist;
- проверить резервное копирование и rollback отдельно;
- включить HTTPS и безопасное хранение secrets;
- проверить audit trail;
- выполнить одну staging-публикацию на каждый provider;
- только затем разрешать production adapter.

## Защита от дублей и lifecycle

Повторная подготовка публикации для того же канала возвращает существующий `draft`/`approved` record с `deduplicated: true`. Архивная кампания не принимает новые публикации. Переходы статусов проверяются сервером, а не только интерфейсом.

## Ошибка внешней генерации

Внешний сервис может вернуть callback только с полем `error` без `result_url`. Тогда job получает статус `failed`, а после исправления причины может быть переведён retry endpoint обратно в `queued`.

## Подпись callback

Если задан `CONTENT_CALLBACK_SECRET`, подписывайте канонический JSON:

```python
import hashlib, hmac, json
payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
```

Передавайте результат в заголовке `X-Content-Signature`. Secret не помещать в Git, README, URL или логи.

## CRM-фильтры

В CRM доступны локальные фильтры очереди контента и кампаний. Они не изменяют данные на сервере и безопасны для staging/demo режима.

## Server-side filtering

Для интеграций можно фильтровать данные без загрузки полного списка:

```text
GET /api/marketing/campaigns?status=active
GET /api/content/jobs?status=failed
```

Недопустимые статусы отклоняются API с ответом `422`.

Публикации конкретной кампании также можно фильтровать:

```text
GET /api/marketing/campaigns/{id}/publications?status=approved
```

Общая очередь публикаций:

```text
GET /api/marketing/publications?status=approved&channel=telegram
```

## Проверка CRM JavaScript

После изменений CRM можно извлечь содержимое `<script>` и проверить командой:

```bash
node --check /tmp/crm.js
```

Проверка не требует credentials и не запускает сервер.

## Диагностика provider-ов

```text
GET /api/marketing/providers
```

`enabled: false` означает, что реальная публикация отключена. `dry_run: true` означает, что локальная проверка через stub допустима.

## Claim внешней content job

Перед передачей задачи внешнему сервису worker должен atomically claim её:

```text
POST /api/content/jobs/{id}/claim
{"provider":"external-video"}
```

Только `queued` задача переходит в `processing`; повторный claim блокируется.


## Cancel content job

Queued или processing job можно отменить из CRM или через `POST /api/content/jobs/{id}/cancel`. После отмены job получает статус `rejected` и audit-запись. Завершённые jobs не отменяются.

## Полный demo/staging workflow кампании

```text
создать кампанию
→ подготовить все каналы
→ проверить очередь
→ одобрить все draft-публикации
→ выполнить dry-run
→ проверить stub external_id по каждому каналу
```

Dry-run не меняет статус публикации и не отправляет данные во внешние сети.

## Campaign attribution

Для просмотра сохранённых UTM и состояния каналов кампании:

```text
GET /api/marketing/campaigns/{id}/attribution
```

Endpoint возвращает только сохранённые данные Campaign Manager. Реальная статистика кликов, CTR и заказов помечается `analytics: not_connected` до подключения аналитической системы.

В CRM UTM можно задать при создании кампании в формате:

```text
utm_source=telegram&utm_campaign=summer-sale&utm_content=video-1
```
