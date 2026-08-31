# Local runtime smoke — 2026-08-31

## Environment
- Local FastAPI app started from `telegram-shop/bot.py` with bot disabled (`BOT_TOKEN` empty).
- Local warehouse URL tested: `http://127.0.0.1:8000/warehouse/`
- Mock Supabase REST server used on `http://127.0.0.1:8010` for direct/proxy contract checks.
- Tests executed after rebuilding code from branch state now in remote `main` and `arena/continue-marketplace-content`.

## Fixes made during smoke
1. Added missing `Store.marketplace_settings()` so site root `/` no longer crashes.
2. Added missing `Store.upsert_product_with_id()` used by `/api/warehouse/direct/mirror`.
3. Adjusted Supabase header logic for modern keys:
   - `sb_publishable_*`
   - `sb_secret_*`
   These keys are now sent via `apikey` only, while legacy JWT-like keys still keep Bearer compatibility.

## Smoke checklist

### A. Warehouse UI/static
- `GET /warehouse/` -> **200 OK**
- `GET /warehouse/app.js` -> **200 OK**
- Confirmed JS bundle contains 3 DB modes:
  - `vps`
  - `supabase_proxy`
  - `supabase_direct`
- Confirmed settings UI code contains `sb-public-key` field.

### B. Warehouse auth
- `POST /api/warehouse/login` with default local admin -> **OK**

### C. VPS / SQLite flow
Tested against real local SQLite:
- `GET /api/warehouse/products` -> **OK**
- `POST /api/warehouse/products` -> **OK**
- `GET /api/warehouse/products/{pid}` -> **OK**
- `PUT /api/warehouse/products/{pid}` -> **OK**
- `POST /api/warehouse/scan` modes:
  - `search` -> **OK**
  - `receive` -> **OK**
  - `sell` -> **OK**
  - `inventory` -> **OK**
- `GET /api/warehouse/scans` -> **OK**
- Temp smoke products were cleaned up after test.

### D. Direct Supabase flow
Warehouse settings temporarily switched to `supabase_direct` with mock values:
- `db_mode = supabase_direct`
- `url = http://127.0.0.1:8010`
- `key = sb_secret_test`
- `public_key = sb_publishable_test`
- `schema = public`
- `table = products`

Checked:
- `PUT /api/warehouse/settings` -> **OK**
- `GET /api/warehouse/settings` masks both `key` and `public_key` -> **OK**
- `GET /api/warehouse/direct/config` returns public direct config -> **OK**
- `GET /api/warehouse/cloud/status` shows `supabase_direct` -> **OK**
- `POST /api/warehouse/direct/next-id` -> **OK**
- `POST /api/warehouse/direct/photos` -> **OK**
- Direct insert into mock Supabase with modern publishable key -> **OK**
- `POST /api/warehouse/direct/mirror` create -> **OK**
- `POST /api/warehouse/direct/mirror` update + scan log -> **OK**
- `POST /api/warehouse/direct/mirror` delete -> **OK**
- Mirrored product readable through VPS API before delete -> **OK**
- Mirrored direct scan visible in `/api/warehouse/scans` -> **OK**

### E. VPS -> Supabase proxy mode
Warehouse settings temporarily switched to `supabase_proxy` with the same mock URL/key pair.
Checked:
- `PUT /api/warehouse/settings` -> **OK**
- `GET /api/warehouse/cloud/status` shows `supabase_proxy` -> **OK**

### F. Site root
- `GET /` -> **200 OK** after adding `marketplace_settings()`.

## Cleanup
- Original warehouse settings were restored after smoke.
- Temporary VPS product and mirrored direct product were removed.

## Conclusion
Local runtime smoke passed for:
- existing VPS / SQLite warehouse flow;
- 3-mode settings plumbing;
- direct config and mirror endpoints;
- modern Supabase key header compatibility;
- proxy/direct mode status switching.

Not covered here:
- real Supabase project credentials;
- real Yandex Object Storage credentials;
- on-device Android manual UX;
- real camera / native scanner behavior on a phone.
