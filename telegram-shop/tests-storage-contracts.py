#!/usr/bin/env python3
"""Контрактные тесты storage-провайдеров (блок 13) — офлайн, без сети и секретов.

Проверяется:
- каждый класс провайдера удовлетворяет Protocol-контракту;
- единый сценарий catalog → upsert_product → upsert_stock → apply_batch
  работает одинаково на SQLiteProvider (реальные операции над duck-typed store);
- ненастроенный/недоступный провайдер даёт понятную ошибку, а не исключение;
- фабрика database_provider_from_cloud возвращает правильный класс на каждый режим;
- provider_status безопасен и никогда не сериализует секреты.

Запуск: cd telegram-shop && python3 tests-storage-contracts.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cloudstore
from storage_contracts import (BackupStorage, DatabaseProvider, PhotoStorage,
                               provider_status)

passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  \u2705 {name}")
    else:
        failed += 1
        print(f"  \u274c {name}{(' — ' + str(extra)) if extra else ''}")


class FakeStore:
    """Duck-typed store для проверки SQLiteProvider без реальной БД."""

    def __init__(self):
        self.rows = {}
        self._next = 1
        self.broken = False

    def _q1(self, sql):
        if self.broken:
            raise RuntimeError("database is locked")
        return {"ok": 1}

    def products(self):
        if self.broken:
            raise RuntimeError("database is locked")
        return [dict(p) for p in self.rows.values()]

    def upsert_product_with_id(self, p):
        if self.broken:
            raise RuntimeError("database is locked")
        pid = int(p.get("id") or 0) or self._next
        self._next = max(self._next, pid + 1)
        cur = dict(self.rows.get(pid) or {}, **p)
        cur["id"] = pid
        self.rows[pid] = cur
        return dict(cur)

    def update_stock_by_code(self, items):
        if self.broken:
            raise RuntimeError("database is locked")
        updated, not_found = 0, []
        for it in items or []:
            code = str((it or {}).get("code") or "")
            rec = next((r for r in self.rows.values() if r.get("code") == code), None)
            if not rec:
                not_found.append(code)
                continue
            if it.get("stock") is not None:
                rec["stock"] = int(it["stock"])
            if it.get("price") is not None:
                rec["price"] = int(it["price"])
            updated += 1
        return {"updated": updated, "not_found": not_found}


print("1) Контракты: классы удовлетворяют Protocol")
s3 = cloudstore.S3Client('', '', '', '')
yd = cloudstore.YandexDiskClient('', 'app:/test')
sb = cloudstore.SupabaseClient('', '', '')
my = cloudstore.MySQLClient('', 3306, '', '', '')
fake = FakeStore()
lite = cloudstore.SQLiteProvider(fake)
ok("S3Client → PhotoStorage", isinstance(s3, PhotoStorage))
ok("YandexDiskClient → PhotoStorage", isinstance(yd, PhotoStorage))
ok("S3Client → DatabaseProvider", isinstance(s3, DatabaseProvider))
ok("SupabaseClient → DatabaseProvider", isinstance(sb, DatabaseProvider))
ok("MySQLClient → DatabaseProvider", isinstance(my, DatabaseProvider))
ok("SQLiteProvider → DatabaseProvider", isinstance(lite, DatabaseProvider))
ok("S3Client → BackupStorage", isinstance(s3, BackupStorage))
ok("YD — только фото-провайдер (не BackupStorage)", not isinstance(yd, BackupStorage))

print("2) Единый сценарий на SQLiteProvider (catalog → product → stock → batch)")
d = lite.catalog()
ok("catalog пуст", d.get("ok") and d["products"] == [], d)
r = lite.upsert_product({"id": 7, "code": "B13-1", "name": "Тест", "price": 100, "stock": 3})
ok("upsert_product ok", r.get("ok") and r.get("count") == 1, r)
d = lite.catalog()
ok("catalog видит товар", d["ok"] and len(d["products"]) == 1 and d["products"][0]["code"] == "B13-1", d)
r = lite.upsert_stock([{"code": "B13-1", "stock": 9, "price": 150}])
ok("upsert_stock обновил", r.get("ok") and r.get("updated") == 1, r)
d = lite.catalog()
p0 = d["products"][0]
ok("stock/price применились", p0["stock"] == 9 and p0["price"] == 150, p0)
r = lite.upsert_stock([{"code": "нет-такого", "stock": 1}])
ok("upsert_stock: неизвестный код → missing", r.get("ok") and r.get("missing") == ["нет-такого"], r)
r = lite.apply_batch([
    {"type": "product", "record": {"id": 8, "code": "B13-2", "name": "Ещё", "price": 5, "stock": 1}},
    {"type": "stock", "items": [{"code": "B13-1", "stock": 10}]},
    {"type": "nonsense"},
])
ok("apply_batch: 2 применено, 1 failed", r.get("applied") == 2 and r.get("failed") == 1, r)
r = lite.push_products([{"id": 9, "code": "B13-3", "name": "Пакет", "price": 1, "stock": 0}])
ok("push_products (полный каталог)", r.get("ok") and r.get("count") == 1, r)

print("3) Недоступный провайдер: понятная ошибка, без исключений")
st = provider_status(s3)
ok("S3 без ключей: ping ok=False", st["ok"] is False and "S3" in (st["error"] or ""), st)
ok("S3 без ключей: статус 503", st.get("status") == 503, st)
st = provider_status(yd)
ok("YD без токена: понятная ошибка", st["ok"] is False and "токен" in (st["error"] or "").lower(), st)
st = provider_status(sb)
ok("Supabase без URL: понятная ошибка", st["ok"] is False and "Supabase" in (st["error"] or ""), st)
st = provider_status(my)
ok("MySQL без host: понятная ошибка", st["ok"] is False and st["error"], st)
r = s3.upsert_stock([{"code": "X", "stock": 1}])
ok("S3 недоступен: upsert_stock даёт ошибку, не исключение", r.get("ok") is False and r.get("error"), r)
r = yd.delete_photo("app:/test/no-such.jpg")
ok("YD недоступен: delete_photo даёт ошибку, не исключение", r.get("ok") is False and r.get("error"), r)
fake.broken = True
st = provider_status(lite)
ok("SQLiteProvider: сломанная БД → 503 без падения", st["ok"] is False and "locked" in (st["error"] or ""), st)
fake.broken = False

print("4) provider_status безопасен")


class Exploder:
    def ping(self):
        raise Exception("s3_secret_key=TOPSECRET leaked")


st = provider_status(Exploder())
ok("исключение поймано", st["ok"] is False and st["status"] == 503, st)
ok("текст ошибки обрезан до 200", len(st["error"]) <= 200, len(st["error"]))

print("5) Фабрика database_provider_from_cloud")
mode, p = cloudstore.database_provider_from_cloud({"db_mode": "vps"})
ok("vps → S3 (каталог-JSON) без store", mode == "vps" and isinstance(p, cloudstore.S3Client), (mode, type(p).__name__))
mode, p = cloudstore.database_provider_from_cloud({"db_mode": "vps"}, store=fake)
ok("vps + store → SQLiteProvider", mode == "vps" and isinstance(p, cloudstore.SQLiteProvider), (mode, type(p).__name__))
mode, p = cloudstore.database_provider_from_cloud({"db_mode": "supabase_proxy", "url": "https://x", "key": "k"})
ok("supabase_proxy → SupabaseClient", mode == "supabase_proxy" and isinstance(p, cloudstore.SupabaseClient), (mode, type(p).__name__))
mode, p = cloudstore.database_provider_from_cloud({"db_mode": "supabase_direct", "url": "https://x", "public_key": "pk"})
ok("supabase_direct → SupabaseClient", mode == "supabase_direct" and isinstance(p, cloudstore.SupabaseClient), (mode, type(p).__name__))
mode, p = cloudstore.database_provider_from_cloud({"db_mode": "mysql", "mysql_host": "h", "mysql_user": "u", "mysql_database": "d"})
ok("mysql → MySQLClient", mode == "mysql" and isinstance(p, cloudstore.MySQLClient), (mode, type(p).__name__))
mode, p = cloudstore.database_provider_from_cloud({})
ok("пустой конфиг → vps по умолчанию", mode == "vps", mode)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
