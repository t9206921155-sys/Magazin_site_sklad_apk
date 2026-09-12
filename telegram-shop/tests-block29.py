#!/usr/bin/env python3
"""Тесты блока 29: бэкенд покупательского приложения (ТЗ §6.2).

GET /api/product/{id}, POST /api/mobile/register, DELETE /api/mobile/devices/{id},
GET /api/mobile/status, ?platform= у /api/app/version, FCM-хук смены статуса заказа.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block29.py [base_url]
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
passed = failed = 0
MARK = f"B29-{int(time.time()) % 100000}"


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  \u2705 {name}")
    else:
        failed += 1
        print(f"  \u274c {name}{(' — ' + str(extra)) if extra else ''}")


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except ValueError:
            return e.code, {}


print("1) Авторизация и товар для карточки")
c, r = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
ok("warehouse login", c == 200 and r.get("token"), f"{c}")
WH = {"X-Wh-Token": r.get("token", "")}
c, r = call("POST", "/admin/api/login", {"password": "admin123"})
ok("admin login", c == 200 and r.get("token"), f"{c}")
AD = {"X-Admin-Token": r.get("token", "")}
c, p = call("POST", "/api/warehouse/products",
            {"name": f"Карточка {MARK}", "price": 777, "stock": 5,
             "purchase_price": 100, "storage_location": "A-1", "owner_name": "внутреннее"},
            WH)
ok("создание товара", c == 201 and p.get("id"), f"{c}")
PID = p.get("id", 0)

print("2) GET /api/product/{id}")
c, r = call("GET", f"/api/product/{PID}")
ok("карточка 200", c == 200, f"{c}")
card = r.get("product", {}) if isinstance(r, dict) else {}
ok("в карточке имя и цена", card.get("name", "").startswith("Карточка") and card.get("price") == 777)
ok("purchase_price скрыта", "purchase_price" not in card)
ok("storage_location скрыт", "storage_location" not in card)
ok("owner_name скрыт", "owner_name" not in card)
ok("есть reviews/review_stats/similar", isinstance(r, dict) and "reviews" in r
   and "review_stats" in r and "similar" in r)
c, _ = call("GET", "/api/product/999999999")
ok("несуществующий → 404", c == 404, f"{c}")
c, _ = call("GET", "/api/product/abc")
ok("мусорный id → 422", c == 422, f"{c}")

print("3) POST /api/mobile/register")
GUEST = f"g29-{MARK}"
c, r = call("POST", "/api/mobile/register",
            {"guest_id": GUEST, "fcm_token": "fcm-test-token-0123456789",
             "platform": "android", "app_version": "1.0.0"})
ok("регистрация", c == 200 and r.get("ok") and r.get("guest_id") == GUEST, f"{c} {r}")
ok("токен наружу не отдаётся", isinstance(r, dict) and "fcm_token" not in r)
c, r = call("POST", "/api/mobile/register",
            {"guest_id": GUEST, "fcm_token": "fcm-test-token-NEW-0123456789"})
ok("upsert заменяет токен", c == 200 and r.get("ok"), f"{c}")
for name, body, want in [
        ("без guest_id → 422", {"fcm_token": "x" * 20}, 422),
        ("короткий токен → 422", {"guest_id": GUEST, "fcm_token": "short"}, 422),
        ("плохая платформа → 422", {"guest_id": GUEST, "fcm_token": "x" * 20,
                                    "platform": "symbian"}, 422)]:
    c, _ = call("POST", "/api/mobile/register", body)
    ok(name, c == want, f"{c}")

print("4) GET /api/mobile/status и DELETE")
c, r = call("GET", "/api/mobile/status")
ok("status 200", c == 200, f"{c}")
ok("dry_run gated", isinstance(r, dict) and r.get("dry_run") is True)
ok("devices >= 1", isinstance(r, dict) and r.get("devices", 0) >= 1, r)
ok("без токенов в статусе", isinstance(r, dict) and "fcm_token" not in json.dumps(r))
c, r = call("DELETE", f"/api/mobile/devices/{GUEST}")
ok("unregister", c == 200 and r.get("removed") is True, f"{c} {r}")
c, r = call("DELETE", f"/api/mobile/devices/{GUEST}")
ok("повторный unregister идемпотентен", c == 200 and r.get("removed") is False, f"{c}")

print("5) /api/app/version?platform=")
c, r = call("GET", "/api/app/version")
ok("без параметра (совместимость)", c == 200 and r.get("platform") == "android", f"{c}")
c, r = call("GET", "/api/app/version?platform=android")
ok("platform=android", c == 200 and r.get("platform") == "android", f"{c}")
c, _ = call("GET", "/api/app/version?platform=ios")
ok("platform=ios → 422", c == 422, f"{c}")

print("6) FCM-хук смены статуса заказа (dry-run)")
OGUEST = f"g29order-{MARK}"
c, r = call("POST", f"/api/order?guest_id={OGUEST}",
            {"items": [{"id": PID, "qty": 1}],
             "customer": {"name": "Тест", "phone": "+70000000000"},
             "delivery_method": "pickup", "payment_method": "test"})
OID = r.get("id") if isinstance(r, dict) else None
ok("создание заказа с guest_id", c == 201 and OID, f"{c}")
if OID:
    c, _ = call("POST", "/api/mobile/register",
                {"guest_id": OGUEST, "fcm_token": "fcm-order-token-0123456789"})
    ok("регистрация устройства покупателя", c == 200, f"{c}")
    c, r = call("POST", f"/admin/api/orders/{OID}/status", {"status": "shipped"}, AD)
    ok("смена статуса (хук внутри)", c == 200 and r.get("status") == "shipped", f"{c}")
    c, r = call("POST", f"/admin/api/orders/{OID}/confirm-payment", {}, AD)
    ok("confirm-payment (хук внутри)", c == 200, f"{c}")

print(f"\nИтого: {passed} ok, {failed} fail")
sys.exit(1 if failed else 0)
