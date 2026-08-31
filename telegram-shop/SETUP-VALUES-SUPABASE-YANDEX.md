# Ready settings: Supabase + Yandex Object Storage

This file gives the exact values and field mapping to enter in `/warehouse/ -> ⚙ Settings`.

## 1) Yandex Object Storage block

Use these exact non-secret values:

- **Preset**: `yandex`
- **Endpoint**: `https://storage.yandexcloud.net`
- **Region**: `ru-central1`
- **Bucket for photos**: `shop-photos`
- **Photo prefix**: `products`
- **Catalog JSON prefix**: `catalog`
- **Bucket for SQLite backup**: `shop-backups`
- **Backup prefix**: `sqlite`
- **Use CDN**: `ON`

Your secret values from Yandex:
- **Access Key**: static access key ID from Yandex service account
- **Secret Key**: static secret access key from Yandex service account

## 2) Supabase block

Common values for both Supabase modes:
- **Supabase URL**: `https://<YOUR_PROJECT_REF>.supabase.co`
- **Schema**: `public`
- **Table / View**: `products`

Keys:
- **Server key for VPS -> Supabase**:
  - use **Secret key** if your dashboard shows modern keys;
  - or **service_role** if your project still shows legacy keys.
- **Direct public key for APK/Web -> Supabase**:
  - use **Publishable key** if your dashboard shows modern keys;
  - or **anon** if your project still shows legacy keys.

## 3) Mode A — VPS / SQLite

Recommended first launch values:
- **Enable external sync / hybrid DB**: `ON` if you want Yandex photo/backup sync, otherwise optional
- **DB mode**: `vps`
- **Supabase URL**: empty
- **Server key**: empty
- **Direct public key**: empty
- Yandex block: fill fully

Result:
- app works through VPS
- SQLite is the live DB
- photos and backups go to Yandex

## 4) Mode B — VPS -> Supabase

Fill:
- **Enable external sync / hybrid DB**: `ON`
- **DB mode**: `supabase_proxy`
- **Supabase URL**: `https://<YOUR_PROJECT_REF>.supabase.co`
- **Server key**: `sb_secret_...` or legacy `service_role`
- **Direct public key**: may stay empty
- **Schema**: `public`
- **Table / View**: `products`
- Yandex block: fill fully

Result:
- APK still logs into VPS
- backend reads/writes catalog in Supabase
- photos and backups still go to Yandex

## 5) Mode C — Direct Supabase

Fill:
- **Enable external sync / hybrid DB**: `ON`
- **DB mode**: `supabase_direct`
- **Supabase URL**: `https://<YOUR_PROJECT_REF>.supabase.co`
- **Server key**: `sb_secret_...` or legacy `service_role`
- **Direct public key**: `sb_publishable_...` or legacy `anon`
- **Schema**: `public`
- **Table / View**: `products`
- Yandex block: fill fully

Result:
- login still stays on VPS
- product catalog + warehouse operations can go direct to Supabase
- VPS mirrors changes back into SQLite
- photos and backups still go to Yandex

## 6) Where to copy values from

### Supabase
- **Project ref**: from your project URL / dashboard
- **URL**: `https://<project-ref>.supabase.co`
- **Modern keys**: Dashboard -> `Settings` -> `API Keys`
  - `Publishable key`
  - `Secret key`
- **Legacy keys** if shown: Dashboard -> `Settings` -> `API Keys` -> `Legacy API Keys`
  - `anon`
  - `service_role`

### Yandex
- Create or choose a **service account** with Object Storage access.
- Create a **static access key** for that service account.
- Copy:
  - key ID -> **Access Key**
  - secret -> **Secret Key**

## 7) Supabase SQL file to run

Run this file in Supabase SQL Editor:
- `telegram-shop/SUPABASE-PRODUCTS-SCHEMA.sql`

Then in direct mode use only the public client key in APK/web, never the server secret key.
