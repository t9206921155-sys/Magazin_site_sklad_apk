# Ручная валидация перед production

Этот список намеренно не выполняется автоматически в песочнице: часть проверок требует реальных устройств, production-домена, облачных credentials, оборудования или большого объёма данных.

## Окружение и зависимости

- [ ] На staging/production установить `requirements.txt` в отдельный venv.
- [ ] Зафиксировать версии через lock-файл после успешной установки.
- [ ] Проверить свободное место: код, venv, pip cache, ffmpeg, логи и backup.
- [ ] При необходимости вынести `imageio-ffmpeg` в `requirements-video.txt`.
- [ ] Проверить запуск без BOT_TOKEN и с реальным BOT_TOKEN отдельно.

## База данных

- [ ] Проверить VPS/SQLite на постоянном диске.
- [ ] Проверить VPS → Supabase с service key только на сервере.
- [ ] Проверить Direct Supabase с RLS и public/anon key.
- [ ] Проверить MySQL/MariaDB через phpMyAdmin: подключение, права, charset utf8mb4, индексы.
- [ ] Сделать тестовый импорт и rollback на копии базы.
- [ ] Сверить товары, заказы, остатки, склады, пользователей и настройки.

## Фото-хранилища

- [ ] Yandex Object Storage: upload, public URL, удаление, CDN.
- [ ] VK Cloud: upload/download и права bucket.
- [ ] Другой S3: endpoint, region, path-style/virtual-host-style.
- [ ] Yandex Disk API: OAuth token, upload URL, overwrite, publish, expired token, rate limit.
- [ ] Проверить загрузку 1 МБ, 10 МБ и пачки фотографий.
- [ ] Проверить, что секреты не попадают в HTML, APK, логи и git.

## Производительность и надёжность

- [ ] Прогнать каталог на реальном количестве товаров.
- [ ] Проверить одновременные сканы с нескольких устройств.
- [ ] Проверить перемещение остатков при параллельных запросах.
- [ ] Проверить offline queue и повторную отправку после восстановления сети.
- [ ] Проверить backup и restore на чистом VPS.
- [ ] Настроить ротацию логов и контроль диска.

## Реальное оборудование

- [ ] Bluetooth HID-сканер.
- [ ] ТСД.
- [ ] Zebra ZPL и Eltron EPL.
- [ ] IP-принтер RAW/JetDirect.
- [ ] Android APK, камера, WebAuthn и биометрия.
- [ ] Реальная сеть склада с плохим Wi-Fi.

## Production smoke

```bash
./deploy/post-deploy-smoke.sh https://YOUR-DOMAIN
```

После smoke дополнительно проверить вручную вход администратора, склад, отчёты, печать и загрузку фото.

## Что не автоматизировать в песочнице

Не запускать здесь массовые миграции, production backup/restore, реальные платежи, реальные 1С-обмены, загрузку больших медиапакетов, тесты на физическом принтере и тесты с боевыми OAuth/S3 credentials.

## Storage layer — ручная проверка после завершения разработки

Автоматические тесты storage-провайдеров отложены по плану. После подключения реальных credentials проверить вручную:

- [ ] `VPS / SQLite`: создать товар, изменить остаток, перезапустить сервис, убедиться в сохранении.
- [ ] `VPS → Supabase`: проверить чтение и запись каталога через backend; service key отсутствует в ответах.
- [ ] `Direct Supabase`: проверить RLS для public/anon key; запретить запись чужого каталога.
- [ ] `MySQL/MariaDB`: подключиться через phpMyAdmin, проверить `utf8mb4`, индексы и права отдельного application user.
- [ ] S3: проверить Yandex Object Storage, VK Cloud и произвольный S3 endpoint отдельно.
- [ ] Yandex Disk: вставить OAuth token, проверить upload URL, overwrite, публикацию, публичную ссылку и протухший token.
- [ ] Проверить переключение photo provider без изменения бизнес-логики.
- [ ] Проверить, что access key, secret key, service key и OAuth token не попадают в HTML, APK, логи и API-ответы.
- [ ] Проверить удаление/замену фото и отсутствие битых ссылок после повторной синхронизации.

Контрактные и интеграционные тесты storage-провайдеров выполнить отдельным этапом после выбора production-провайдера и получения тестовых credentials.

## SQLite restore helper

Безопасная предварительная проверка backup выполняется без замены базы:

```bash
python3 telegram-shop/scripts/restore_sqlite.py /path/to/shop.db.backup
```

Фактическая замена выполняется только явно:

```bash
python3 telegram-shop/scripts/restore_sqlite.py /path/to/shop.db.backup --target telegram-shop/data/shop.db --apply
```

Перед `--apply` остановить приложение и сохранить текущую базу отдельной копией.

## Перенос в MySQL/MariaDB через phpMyAdmin

Сначала сделать SQL-экспорт и проверить его на копии:

```bash
python3 telegram-shop/scripts/export_sqlite_sql.py telegram-shop/data/shop.db -o /tmp/shop-export.sql
```

Затем импортировать `/tmp/shop-export.sql` через phpMyAdmin в отдельную тестовую базу с кодировкой `utf8mb4`. Автоматический production-импорт не выполняется.

## Скриншоты для ручной приёмки

Для каждого пункта при ручной проверке сохранять скриншот с датой и окружением (`staging`/`production`). Не включать в кадр пароли, OAuth-токены, service keys, персональные данные покупателей и полные URL с секретными query-параметрами.

### База данных

- [ ] VPS / SQLite: экран настроек и сохранение после перезапуска.
- [ ] VPS → Supabase: настройки режима и результат cloud test.
- [ ] Direct Supabase: Supabase RLS policy и успешный/запрещённый запрос.
- [ ] MySQL/MariaDB: phpMyAdmin — структура таблиц, `utf8mb4`, пользователь приложения без лишних прав.
- [ ] Restore: dry-run, integrity check и восстановленная контрольная запись.

### Фото

- [ ] S3 Yandex: bucket/prefix без секретных ключей и открытая тестовая фотография.
- [ ] VK Cloud: bucket и открытая тестовая фотография.
- [ ] Другой S3: endpoint без credentials и результат загрузки.
- [ ] Yandex Disk: выбранный provider, путь, успешная загрузка и публичная ссылка; OAuth token замазать.

### Production

- [ ] `/health/live` и `/health/ready` с HTTP-кодами.
- [ ] полный `post-deploy-smoke.sh`.
- [ ] backup в bucket.
- [ ] восстановление на отдельной базе.
- [ ] Android/PWA: каталог, склад, сканирование и печать на реальном устройстве.

Рекомендуемый шаблон имени:

```text
screenshots/{block}/{environment}-{check}-{YYYY-MM-DD}.png
```
