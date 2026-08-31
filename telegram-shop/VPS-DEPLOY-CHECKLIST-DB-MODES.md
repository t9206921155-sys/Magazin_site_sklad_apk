# VPS deploy checklist: 3 DB modes + Yandex Object Storage

## 1. How connection works

There are now 3 database modes in warehouse settings:

1. `VPS / SQLite`
2. `VPS -> Supabase`
3. `Direct Supabase`

But the APK entry point is still simple:

`APK / browser -> your VPS warehouse URL`

Example in the APK:
- `https://your-domain/warehouse/`

Then, depending on the selected mode:

### Mode 1 — VPS / SQLite
- APK -> VPS backend
- backend reads/writes `data/shop.db`
- photos go to Yandex Object Storage
- SQLite backup goes to Yandex Object Storage

### Mode 2 — VPS -> Supabase
- APK -> VPS backend
- backend reads/writes catalog in Supabase
- photos still go to Yandex Object Storage
- SQLite backup still goes to Yandex Object Storage

### Mode 3 — Direct Supabase
- APK first logs in through VPS as usual
- after login the warehouse app receives direct public config from VPS
- then product catalog operations go directly to Supabase
- VPS mirrors direct changes back into local SQLite for storefront, orders and service APIs
- photos still go through VPS/Yandex flow
- SQLite backup still goes to Yandex Object Storage

## 2. What the user enters where

### In APK
Only one URL:
- `https://your-domain/warehouse/`

### In warehouse settings

#### DB mode selector
Choose one:
- `VPS / SQLite — живая база на сервере`
- `VPS → Supabase — backend работает с Supabase`
- `Direct Supabase — приложение работает с Supabase напрямую`

#### Supabase fields
- `Supabase URL`
- `Server key для VPS → Supabase`
- `Direct public/anon key для APK/Web → Supabase`
- `Schema`
- `Table / View`

#### Yandex Object Storage fields
- `Preset = Яндекс`
- `Endpoint = https://storage.yandexcloud.net`
- `Access Key`
- `Secret Key`
- `Bucket для фото = shop-photos`
- `Photo prefix = products`
- `Catalog JSON prefix = catalog`
- `Bucket для backup SQLite = shop-backups`
- `Backup prefix = sqlite`
- `Region = ru-central1`

## 3. Recommended setup order

### First start safely
Recommended first production setup:
1. configure Yandex Object Storage
2. choose `VPS / SQLite`
3. verify upload and backup
4. then test `VPS -> Supabase`
5. only after that enable `Direct Supabase`

## 4. Before deploy on VPS

Prepare:
- VPS with the project already running
- working `/warehouse/` URL
- Yandex Object Storage keys
- optional Supabase project

Make local SQLite backup:

```bash
cp -f telegram-shop/data/shop.db telegram-shop/data/shop.db.before-hybrid-db.bak
```

## 5. Pull latest code

```bash
cd /path/to/repo
git fetch origin
git checkout main
git pull origin main
```

Or with helper:

```bash
bash deploy/deploy.sh --branch main
```

## 6. Restart app

If Docker Compose:

```bash
docker compose up -d --build
```

## 7. Configure Supabase table

Run SQL from file:
- `telegram-shop/SUPABASE-PRODUCTS-SCHEMA.sql`

Open Supabase SQL Editor and execute it.

## 8. Configure each mode

### A. VPS / SQLite
Select:
- `VPS / SQLite — живая база на сервере`

Then:
1. save
2. `Проверить`
3. `Синхронизировать`
4. `Бэкап БД`

### B. VPS -> Supabase
Select:
- `VPS → Supabase — backend работает с Supabase`

Fill:
- Supabase URL
- Server key
- Schema = `public`
- Table = `products`

Then:
1. save
2. `Проверить`
3. `Синхронизировать`
4. if needed `⬇️ Из облака`

### C. Direct Supabase
Select:
- `Direct Supabase — приложение работает с Supabase напрямую`

Fill:
- Supabase URL
- Server key for VPS mirror/sync
- Direct public/anon key for the app
- Schema = `public`
- Table = `products`

Then:
1. save
2. `Проверить`
3. reload warehouse app
4. create/edit one product
5. verify it appears in Supabase
6. verify it is mirrored on VPS too

## 9. Post-deploy test

Check:
- `/warehouse/` opens
- settings show 3 DB modes
- Yandex block is separate from DB block
- `Проверить` works
- `Синхронизировать` works
- one product can be created
- one product can be edited
- scan receive/sell works
- one photo uploads to Yandex
- backup file appears in Yandex bucket
- APK still opens by the same VPS URL

## 10. Important security note

For direct mode:
- use only the Supabase public/anon key in the app
- do not put service_role into the APK/web client
- keep service_role only on VPS
- RLS in Supabase must be enabled for the `products` table
