# 🗄 VPS + Yandex Object Storage — рекомендуемая схема запуска склада

Это целевая схема для данного проекта:

- **VPS**
  - backend / API
  - `/warehouse/`
  - `/admin`
  - живая база `telegram-shop/data/shop.db`
- **Yandex Object Storage**
  - bucket `shop-photos` — фото товаров
  - bucket `shop-backups` — резервные копии SQLite

Важно: APK подключается **к серверу на VPS**, а не напрямую к Object Storage.

---

## 1. Что где хранится

### На VPS
- все пользователи склада
- остатки
- карточки товаров
- настройки
- журнал действий
- файл базы: `telegram-shop/data/shop.db`

### В Yandex Object Storage
- фото товаров
- JSON-копия каталога
- резервные копии базы `shop.db`

---

## 2. Что нужно создать в Yandex Cloud

### Bucket для фото
Создайте bucket:

```text
shop-photos
```

### Bucket для резервных копий
Создайте bucket:

```text
shop-backups
```

### Доступ
Нужны AWS-совместимые S3-ключи:
- `Access Key`
- `Secret Key`

Endpoint для Яндекса:

```text
https://storage.yandexcloud.net
```

Region:

```text
ru-central1
```

---

## 3. Что настроить в складе

Откройте:

```text
http://IP_СЕРВЕРА/warehouse/
```

Далее:

**⚙ Настройки → Облако**

Заполните так:

### База товаров
- **Режим базы**: `VPS / SQLite — живая база на сервере`

### Фото и backup
- **Preset**: `Яндекс — Объектное хранилище`
- **Endpoint**: `https://storage.yandexcloud.net`
- **Access Key**: ваш ключ Яндекса
- **Secret Key**: ваш секрет Яндекса
- **Bucket для фото**: `shop-photos`
- **Регион**: `ru-central1`
- **Папка/префикс для фото**: `products`
- **Папка/префикс для catalog JSON**: `catalog`
- **Bucket для backup SQLite**: `shop-backups`
- **Папка/префикс для backup SQLite**: `sqlite`

Потом нажмите по порядку:

1. `Сохранить`
2. `Проверить`
3. `Синхронизировать`
4. `Бэкап БД`

И включите:
- `Подтягивать фото с облака`
- при желании `Автосинхронизация фото при сохранении товара`

---

## 4. Что делает проект после этой настройки

### Фото
Новые и существующие фото можно выгрузить в:

```text
https://storage.yandexcloud.net/shop-photos/products/...
```

### Каталог
Копия каталога кладётся в bucket фото в JSON-файл:

```text
shop-photos/catalog/products.json
```

### SQLite backup
Ручной backup создаёт снимок живой БД и загружает его в:

```text
s3://shop-backups/sqlite/shop-YYYYMMDD-HHMMSS.db
```

---

## 5. Автоматический backup по cron

После того как облачные настройки уже сохранены в складе, на VPS можно включить cron.

Откройте cron:

```bash
crontab -e
```

Добавьте, например, backup каждые 6 часов:

```cron
0 */6 * * * cd /opt/Magazin_site_sklad_apk && /usr/bin/python3 telegram-shop/scripts/backup_sqlite_to_s3.py >> /var/log/telegram-shop-backup.log 2>&1
```

Если путь к проекту другой — замените `/opt/Magazin_site_sklad_apk`.

---

## 6. Как проверить, что всё работает

### Проверка фото
1. добавить товар или открыть существующий;
2. прикрепить фото;
3. нажать `Синхронизировать`;
4. убедиться, что в карточке товара фото открывается нормально.

### Проверка backup
1. нажать `Бэкап БД`;
2. открыть Yandex bucket `shop-backups`;
3. убедиться, что появился файл вида:

```text
sqlite/shop-20260830-120000.db
```

---

## 7. Подключение APK

В APK укажите адрес:

```text
http://IP_СЕРВЕРА/warehouse/
```

Когда появится домен и HTTPS, лучше заменить адрес на:

```text
https://ваш-домен/warehouse/
```

---

## 8. Итоговая архитектура

### Рабочая база
- живёт на VPS в `data/shop.db`

### Фото
- хранятся в `shop-photos`

### Резервные копии
- хранятся в `shop-backups`

### APK
- работает через ваш сервер и API на VPS
