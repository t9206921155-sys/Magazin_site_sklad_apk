# Блок 13 — Единый storage layer

**Статус:** ⏳ запланировано

## Цель
Унифицировать подключение SQLite, Supabase, MySQL/MariaDB, S3 и Yandex Disk через явные provider-интерфейсы.

## Задачи
- [ ] `DatabaseProvider`: ping, catalog, product, stock, transaction.
- [ ] `PhotoStorage`: ping, upload, delete, public_url.
- [ ] Привести S3 и Yandex Disk к единому интерфейсу.
- [ ] Убрать разрозненные проверки режимов из UI.
- [ ] Маскирование секретов и валидация конфигурации.
- [ ] Контрактные тесты каждого провайдера.

## Приёмка
- [ ] смена провайдера не требует изменения бизнес-логики.
- [ ] недоступный provider даёт понятную ошибку.
- [ ] service-role и OAuth secrets не уходят клиенту.

## Отчёт (текущий этап)

- Добавлены `DatabaseProvider` и `PhotoStorage` contracts.
- Добавлена общая фабрика `database_provider_from_cloud`.
- S3 и Yandex Disk поддерживают ping, upload, public URL и delete.
- Добавлены `/api/warehouse/cloud/providers` и `/api/warehouse/cloud/config-check`.
- Диагностика корректно показывает выбранный photo provider.
- Добавлены безопасные contract tests без credentials.
- Ручные проверки реальных Supabase, MySQL, S3 и Yandex Disk отложены до staging.
