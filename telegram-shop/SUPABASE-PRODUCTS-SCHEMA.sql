-- Supabase schema for telegram-shop warehouse
-- Supports 3 DB modes:
-- 1) VPS / SQLite
-- 2) VPS -> Supabase
-- 3) Direct Supabase
--
-- Media and SQLite backups remain in Yandex Object Storage.
-- For Direct Supabase with warehouse login still going through VPS,
-- the client uses a public/anon key, so RLS below grants access to role anon
-- only for this products table.

create extension if not exists pgcrypto;

create table if not exists public.products (
    id bigint primary key,
    code text not null default '',
    name text not null,
    category text not null default '',
    price integer not null default 0,
    old_price integer not null default 0,
    stock integer not null default -1,
    description text not null default '',
    photo text not null default '',
    photos jsonb not null default '[]'::jsonb,
    storage_location text not null default '',
    owner_name text not null default '',
    barcode text not null default '',
    on_showcase boolean not null default true,
    in_stock boolean not null default true,
    purchase_price integer not null default 0,
    is_archived boolean not null default false,
    condition text not null default 'new',
    subcategory text not null default '',
    params jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    constraint products_condition_check check (condition in ('new', 'used', 'defect'))
);

create index if not exists idx_products_category on public.products (category);
create index if not exists idx_products_barcode on public.products (barcode);
create index if not exists idx_products_updated_at on public.products (updated_at desc);
create index if not exists idx_products_archived on public.products (is_archived);

create or replace function public.set_products_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_products_updated_at on public.products;
create trigger trg_products_updated_at
before update on public.products
for each row
execute function public.set_products_updated_at();

comment on table public.products is 'Warehouse catalog table for telegram-shop sync and direct mode';
comment on column public.products.photos is 'JSON array of photo URLs or local VPS paths';
comment on column public.products.params is 'Extra product params JSON';

alter table public.products enable row level security;

-- Clean old policies if names already exist.
drop policy if exists products_read_all on public.products;
drop policy if exists products_write_all on public.products;

-- Direct mode uses anon/public key after VPS login.
create policy products_read_all on public.products
for select
to anon, authenticated
using (true);

create policy products_write_all on public.products
for all
to anon, authenticated
using (true)
with check (true);

-- Notes:
-- 1. In warehouse settings set:
--    Schema: public
--    Table / View: products
-- 2. Server key stays only on VPS.
-- 3. Direct mode key should be the public/anon key, never service_role in APK/web.
-- 4. Because direct mode writes from the client, keep access limited to this table only.
