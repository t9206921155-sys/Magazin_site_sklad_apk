# Блок 22 — Wildberries: ресейл и marketplace-интеграция

**Статус:** ⏳ запланировано

## Цель
Проверить возможность легальной интеграции с Wildberries для сценария ресейла и не смешивать её с обычной витриной магазина.

## Предварительный аудит

- [ ] уточнить, имеется в виду официальный WB API, WB Resale/комиссионный сценарий или публикация товаров продавца;
- [ ] проверить доступность API для типа аккаунта и региона;
- [ ] получить официальную документацию и тестовые credentials;
- [ ] проверить правила публикации бывших в употреблении товаров;
- [ ] проверить требования к маркировке, SKU, фото, категориям и остаткам;
- [ ] определить, поддерживает ли API создание объявлений, остатки, цены, заказы и статусы.

## Реализация после подтверждения API

- [ ] отдельный `WildberriesProvider` adapter;
- [ ] OAuth/API token только на backend;
- [ ] mapping категории, состояния, бренда, размера и параметров;
- [ ] синхронизация SKU, цены, остатков и фото;
- [ ] статусы модерации и ошибки;
- [ ] idempotency и защита от дублей;
- [ ] журнал синхронизации;
- [ ] dry-run и sandbox, если доступны;
- [ ] ручное подтверждение первой публикации;
- [ ] не использовать scraping и не обходить ограничения WB.

## Приёмка

- [ ] тестовая публикация через официальный API/feed;
- [ ] корректное обновление цены и остатка;
- [ ] корректное снятие товара;
- [ ] ошибочная категория не ломает очередь;
- [ ] screenshots кабинета и результата без секретов.

## Текущий кодовый этап

- Добавлена безопасная граница `WildberriesProvider` без scraping.
- Без официального token/provider audit публикация намеренно отключена.
- Доступно только формирование базового mapping товара и диагностическое сообщение.

## Official API audit checklist

- [ ] Confirm seller account and legal entity access.
- [ ] Confirm official WB API endpoint and current documentation.
- [ ] Confirm token scope and storage method without committing secrets.
- [ ] Confirm product/card creation, stocks, prices and order capabilities.
- [ ] Confirm rate limits, sandbox availability and error formats.
- [ ] Validate one staging operation manually before enabling any provider method.
- [ ] Keep scraping, browser automation and unofficial endpoints disabled.
