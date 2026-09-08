#!/usr/bin/env python3
"""Тесты блока 16: Marketplace 2.0 — подписки, бронь, жалобы/чёрный список,
просмотры витрины, поднятие объявлений. Права buyer/seller/admin покрыты отдельно.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block16.py [base_url]
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
passed = failed = 0
MARK = f"B16-{int(time.time()) % 100000}"


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
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


print("0) Подготовка: админ, продавец, товары")
c, r = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
assert c == 200, r
HA = {"X-WH-Token": r["token"]}
c, r = call("POST", "/admin/api/login", {"password": "admin123"})
assert c == 200, r
AD = {"X-Admin-Token": r["token"]}

c, r = call("POST", "/api/seller/register",
            {"store_name": f"{MARK} витрина", "phone": "+7 900 000-16-16",
             "description": "тест блока 16"})
assert c == 201, (c, r)
SKEY = {"X-Seller-Key": r["key"]}
SLUG = r["slug"]
ok("продавец зарегистрирован", bool(SKEY["X-Seller-Key"]) and bool(SLUG), r)

# активируем продавца админом
c, sellers = call("GET", "/admin/api/sellers", None, AD)
sid = next((s["id"] for s in sellers if s["slug"] == SLUG), 0)
ok("админ видит продавца", bool(sid), sid)
c, r = call("POST", f"/admin/api/sellers/{sid}/status", {"status": "active"}, AD)
ok("админ активировал продавца", c == 200, (c, r))

c, prod = call("POST", "/api/seller/products",
               {"name": f"{MARK} товар", "price": 1000, "stock": 2,
                "description": "для брони и подписок"}, SKEY)
assert c == 201, (c, prod)
PID = prod["id"]
ok("товар продавца создан", bool(PID), prod)

# складской товар без seller (контроль выдачи)
c, wp = call("POST", "/api/warehouse/products",
             {"name": f"{MARK} обычный", "price": 500, "stock": 5}, HA)
WPID = wp["id"]

cleanup = {"seller_id": sid, "product_id": PID, "warehouse_id": WPID}

try:
    print("1) Подписки на витрины и лента новинок")
    BUYER = f"buyer-{MARK}"
    c, r = call("POST", f"/api/sellers/{SLUG}/subscribe", {"user_key": BUYER})
    ok("подписка прошла", c == 200 and r.get("subscribed") is True, (c, r))
    ok("subscribers=1", r.get("subscribers") == 1, r)
    c, r = call("POST", f"/api/sellers/{SLUG}/subscribe", {"user_key": BUYER})
    ok("повторная подписка не дублируется", c == 200 and r.get("subscribers") == 1, r)
    c, r = call("POST", f"/api/sellers/{SLUG}/subscribe", {"user_key": "x"})
    ok("короткий user_key → 422", c == 422, c)
    c, r = call("GET", "/api/my/subscriptions?" + urllib.parse.urlencode({"user_key": BUYER}))
    stores = r.get("stores") or []
    ok("лента подписок содержит витрину", c == 200 and any(s["slug"] == SLUG for s in stores), r)
    mine = next((s for s in stores if s["slug"] == SLUG), {})
    ok("в ленте есть новинки (товар продавца)",
       any(p["id"] == PID for p in (mine.get("latest") or [])), mine.get("latest"))
    c, r = call("POST", f"/api/sellers/{SLUG}/unsubscribe", {"user_key": BUYER})
    ok("отписка прошла", c == 200 and r.get("subscribed") is False and r.get("subscribers") == 0, r)
    c, r = call("POST", f"/api/sellers/{SLUG}/unsubscribe", {"user_key": BUYER})
    ok("повторная отписка идемпотентна", c == 200 and r.get("subscribed") is False, r)
    c, r = call("POST", f"/api/sellers/nosuchslug-16/subscribe", {"user_key": BUYER})
    ok("подписка на несуществующую витрину → 404", c == 404, c)

    print("2) Бронь товара")
    c, r = call("POST", "/api/reservations",
                {"product_id": PID, "buyer_key": BUYER, "qty": 1})
    ok("бронь создана", c == 201 and r.get("status") == "active", (c, r))
    RID = r.get("id")
    ok("есть срок истечения", bool(r.get("expires_at")), r.get("expires_at"))
    c, r = call("GET", "/api/reservations?" + urllib.parse.urlencode({"buyer_key": BUYER}))
    ok("бронь видна покупателю с товаром",
       c == 200 and any(x["id"] == RID and (x.get("product") or {}).get("id") == PID
                        for x in (r.get("reservations") or [])), r)
    c, r = call("POST", "/api/reservations",
                {"product_id": PID, "buyer_key": BUYER, "qty": 99})
    ok("бронь больше остатка → 422", c == 422, (c, r))
    c, r = call("POST", "/api/reservations", {"product_id": 999999, "buyer_key": BUYER})
    ok("бронь несуществующего → 422/404", c in (404, 422), c)
    OTHER = f"other-{MARK}"
    c, r = call("DELETE", f"/api/reservations/{RID}", {"buyer_key": OTHER})
    ok("чужой покупатель не может отменить бронь (403)", c == 403, (c, r))
    c, r = call("DELETE", f"/api/reservations/{RID}", {"buyer_key": BUYER})
    ok("свою бронь отменил", c == 200 and r.get("status") == "cancelled", (c, r))
    c, r = call("DELETE", "/api/reservations/999999", {"buyer_key": BUYER})
    ok("отмена несуществующей брони → 404", c == 404, c)

    print("3) Жалобы, модерация, чёрный список")
    c, r = call("POST", "/api/complaints",
                {"product_id": PID, "reporter_key": BUYER, "reason": "fraud",
                 "text": "Продавец прислал не тот товар, прошу проверить"})
    ok("жалоба создана", c == 201 and r.get("status") == "pending", (c, r))
    ok("жалоба привязана к продавцу", r.get("seller_id") == sid, r)
    CID = r.get("id")
    c, r = call("POST", "/api/complaints", {"product_id": PID, "reporter_key": BUYER, "text": "коротко"})
    ok("жалоба без текста → 422", c == 422, c)
    c, r = call("GET", "/admin/api/complaints?status=pending", None, AD)
    ok("админ видит жалобу", c == 200 and any(x["id"] == CID for x in (r.get("complaints") or [])), r)
    c, r = call("GET", "/admin/api/complaints", None, {"X-Admin-Token": "wrong"})
    ok("жалобы без админ-токена → 403", c == 403, c)
    c, r = call("GET", "/api/catalog?" + urllib.parse.urlencode({"q": MARK}))
    ok("до бана товар в выдаче", any(p["id"] == PID for p in r.get("products", [])))

    c, r = call("POST", f"/admin/api/complaints/{CID}/resolve",
                {"status": "resolved", "resolution": "подтверждено, продавец забанен",
                 "ban_seller": True}, AD)
    ok("жалоба решена админом", c == 200 and r.get("status") == "resolved", (c, r))
    c, r = call("GET", "/admin/api/sellers", None, AD)
    st = next((s["status"] for s in r if s["id"] == sid), "?")
    ok("продавец в чёрном списке (banned)", st == "banned", st)
    c, r = call("GET", "/api/catalog?" + urllib.parse.urlencode({"q": MARK}))
    ok("товары забаненного исчезли из выдачи",
       all(p["id"] != PID for p in r.get("products", [])), [p["id"] for p in r.get("products", [])])
    c, _ = call("GET", f"/seller/{SLUG}")
    ok("витрина забанного → 404", c == 404, c)
    c, r = call("POST", f"/admin/api/sellers/{sid}/ban", {"banned": False}, AD)
    ok("разбан возвращает продавца", c == 200 and r.get("seller", {}).get("status") == "active", (c, r))
    c, r = call("GET", "/api/catalog?" + urllib.parse.urlencode({"q": MARK}))
    ok("после разбана товар снова в выдаче", any(p["id"] == PID for p in r.get("products", [])))

    print("4) Просмотры витрины и счётчик подписчиков")
    for _ in range(3):
        call("GET", f"/seller/{SLUG}")
    c, r = call("GET", "/admin/api/sellers", None, AD)
    srow = next((s for s in r if s["id"] == sid), {})
    ok("просмотры копятся (>=3)", int(srow.get("views") or 0) >= 3, srow.get("views"))

    print("5) Продвижение: «поднять объявление»")
    c, r = call("POST", f"/api/seller/products/{PID}/boost", None, SKEY)
    ok("буст прошёл", c == 200 and bool(r.get("boosted_until")), (c, r))
    boosted_until = r.get("boosted_until")
    c, r = call("POST", f"/api/seller/products/{PID}/boost", None, SKEY)
    ok("повторный буст сразу → 409", c == 409, c)
    c, r = call("POST", f"/api/seller/products/{WPID}/boost", None, SKEY)
    ok("чужой товар не поднять (не продавец)", c in (403, 404, 409), c)
    # порядок выдачи по умолчанию: поднятый — раньше обычного
    c, d = call("GET", "/api/catalog?" + urllib.parse.urlencode({"q": MARK}))
    ids = [p["id"] for p in d.get("products", [])]
    ok("поднятое объявление выше в выдаче", PID in ids and WPID in ids and ids.index(PID) < ids.index(WPID), ids)
    # при явной сортировке буст не мешает
    c, d = call("GET", "/api/catalog?" + urllib.parse.urlencode({"q": MARK, "sort": "price_asc"}))
    ids = [p["id"] for p in d.get("products", [])]
    ok("сортировка по цене приоритетнее буста (500₽ первый)", ids == [WPID, PID], ids)

    print("6) Права: seller/admin/buyer границы")
    c, r = call("POST", "/api/seller/products/999999/boost", None, SKEY)
    ok("буст несуществующего товара → 404/409", c in (404, 409), c)
    c, r = call("POST", f"/api/seller/products/{PID}/boost", None, {"X-Seller-Key": "bad-key"})
    ok("буст без ключа продавца → 403", c == 403, c)
    c, r = call("POST", "/admin/api/sellers/999999/ban", {"banned": True}, AD)
    ok("бан несуществующего продавца → 404", c == 404, c)

finally:
    print("7) Очистка")
    c, _ = call("PUT", f"/api/warehouse/products/{WPID}", {"is_archived": True, "in_stock": False}, HA)
    ok("складской товар архивирован", c == 200, c)
    if cleanup["product_id"]:
        c, _ = call("DELETE", f"/api/seller/products/{cleanup['product_id']}", None, SKEY)
        ok("товар продавца удалён", c in (200, 404), c)
    c, _ = call("POST", f"/admin/api/sellers/{sid}/status", {"status": "pending"}, AD)
    ok("продавец деактивирован", c == 200, c)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
