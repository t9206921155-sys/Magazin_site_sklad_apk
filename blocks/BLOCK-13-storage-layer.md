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
