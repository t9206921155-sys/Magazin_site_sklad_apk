"""Тесты блока 06: мультисклад и роли.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block06.py [base_url]
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
passed = failed = 0


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


c, tok = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
assert c == 200, f"вход не удался: {c} {tok}"
HA = {"X-WH-Token": tok["token"]}

print("0) Подготовка")
c, prod = call("POST", "/api/warehouse/products",
               {"name": "Блок06 тест", "price": 100, "stock": 20,
                "sku": "B06", "code": "B06-CODE", "barcode": "4600000000606"}, HA)
pid = prod.get("id")
ok("тестовый товар создан", bool(pid), prod)

c, whs = call("GET", "/api/warehouse/warehouses", None, HA)
ok("список складов доступен", c == 200 and whs.get("warehouses"), whs)
w1 = whs["default"]

name2 = "Тестовый-Б06"
existing = [w for w in whs["warehouses"] if w["name"] == name2]
if existing:
    w2 = existing[0]["id"]
else:
    c, w = call("POST", "/api/warehouse/warehouses", {"name": name2}, HA)
    ok("второй склад создан", c == 201, w)
    w2 = w["id"]

print("1) Миграция сохранила остатки")
c, br = call("GET", f"/api/warehouse/products/{pid}/stock", None, HA)
ok("новый товар попал в разбивку", c == 200 and br["total"] == 20, br)

print("2) Дубль имени склада отклоняется")
c, r = call("POST", "/api/warehouse/warehouses", {"name": name2}, HA)
ok("дубль -> 422", c == 422, r)
c, r = call("POST", "/api/warehouse/warehouses", {"name": "   "}, HA)
ok("пустое имя -> 422", c == 422, r)

print("3) Перемещение между складами")
c, r = call("POST", "/api/warehouse/transfer",
            {"product_id": pid, "from": w1, "to": w2, "qty": 8}, HA)
ok("перемещение прошло", c == 200 and r.get("qty") == 8, r)
ok("списано с источника", r.get("src_left") == 12, r)
ok("приходовано на приёмник", r.get("dst_now") == 8, r)
ok("сумма не изменилась", r.get("total") == 20, r)

c, r = call("POST", "/api/warehouse/transfer",
            {"product_id": pid, "from": w1, "to": w2, "qty": 9999}, HA)
ok("перемещение больше остатка -> 400", c == 400, r)
c, r = call("POST", "/api/warehouse/transfer",
            {"product_id": pid, "from": w1, "to": w1, "qty": 1}, HA)
ok("перемещение в тот же склад -> 400", c == 400, r)
c, r = call("POST", "/api/warehouse/transfer",
            {"product_id": pid, "from": w1, "to": w2, "qty": 0}, HA)
ok("нулевое количество -> 400", c == 400, r)
c, r = call("POST", "/api/warehouse/transfer",
            {"product_id": 999999, "from": w1, "to": w2, "qty": 1}, HA)
ok("несуществующий товар -> 404", c == 404, r)

print("4) Суммарный остаток = сумме по складам")
c, br = call("GET", f"/api/warehouse/products/{pid}/stock", None, HA)
ok("сумма строк равна total",
   sum(x["qty"] for x in br["rows"]) == br["total"] == 20, br)
c, p = call("GET", f"/api/warehouse/products/{pid}", None, HA)
item = (p.get("products") or [{}])[0]
ok("витрина видит суммарный остаток", item.get("stock") == 20, item)

print("5) Сканирование привязано к складу")
c, r = call("POST", "/api/warehouse/scan",
            {"code": "4600000000606", "mode": "sell", "qty": 3, "warehouse_id": w2}, HA)
ok("продажа со склада 2", c == 200 and r.get("found"), r)
c, br = call("GET", f"/api/warehouse/products/{pid}/stock", None, HA)
by = {x["warehouse_id"]: x["qty"] for x in br["rows"]}
ok("списалось именно со склада 2", by.get(w2) == 5, by)
ok("склад 1 не тронут", by.get(w1) == 12, by)
ok("сумма пересчитана", br["total"] == 17, br)

c, r = call("POST", "/api/warehouse/scan",
            {"code": "4600000000606", "mode": "receive", "qty": 4, "warehouse_id": w1}, HA)
c, br = call("GET", f"/api/warehouse/products/{pid}/stock", None, HA)
by = {x["warehouse_id"]: x["qty"] for x in br["rows"]}
ok("приёмка на склад 1", by.get(w1) == 16 and br["total"] == 21, br)

print("6) Роли и доступы")
call("POST", "/api/warehouse/users",
     {"login": "b06worker", "name": "Тест-кладовщик",
      "password": "b06pass", "role": "worker"}, HA)
c, users = call("GET", "/api/warehouse/users", None, HA)
wid_user = next((u["id"] for u in users if u["login"] == "b06worker"), None)
ok("сотрудник создан", bool(wid_user), users)

c, r = call("PUT", f"/api/warehouse/users/{wid_user}/warehouses",
            {"warehouse_ids": [w2]}, HA)
ok("доступ выдан только к складу 2", c == 200 and r["warehouse_ids"] == [w2], r)

c, wt = call("POST", "/api/warehouse/login",
             {"login": "b06worker", "password": "b06pass"})
HW = {"X-WH-Token": wt["token"]}

c, r = call("GET", "/api/warehouse/warehouses", None, HW)
ok("сотрудник видит только свой склад",
   [x["id"] for x in r["warehouses"]] == [w2], r)

c, r = call("POST", f"/api/warehouse/products/{pid}/stock",
            {"warehouse_id": w1, "qty": 100}, HW)
ok("чужой склад на запись -> 403", c == 403, r)
c, r = call("POST", "/api/warehouse/transfer",
            {"product_id": pid, "from": w1, "to": w2, "qty": 1}, HW)
ok("перемещение с чужого склада -> 403", c == 403, r)
c, r = call("POST", "/api/warehouse/warehouses", {"name": "Левый"}, HW)
ok("создание склада сотрудником -> 403", c == 403, r)
c, r = call("POST", f"/api/warehouse/products/{pid}/stock",
            {"warehouse_id": w2, "qty": 7}, HW)
ok("свой склад доступен", c == 200 and r["qty"] == 7, r)

print("7) Удаление склада")
c, r = call("DELETE", f"/api/warehouse/warehouses/{w2}", None, HA)
ok("склад с остатками -> 409", c == 409, r)
call("POST", "/api/warehouse/transfer",
     {"product_id": pid, "from": w2, "to": w1, "qty": 7}, HA)
c, r = call("DELETE", f"/api/warehouse/warehouses/{w2}", None, HA)
ok("пустой склад удаляется", c == 200, r)
c, r = call("DELETE", f"/api/warehouse/warehouses/{w1}", None, HA)
ok("единственный склад не удаляется", c == 409, r)

print("8) Доступ без токена")
c, _ = call("GET", "/api/warehouse/warehouses")
ok("без токена -> 403", c == 403)

print("\nОчистка")
if wid_user:
    call("DELETE", f"/api/warehouse/users/{wid_user}", None, HA)
if pid:
    c, _ = call("DELETE", f"/api/warehouse/products/{pid}", None, HA)
    ok("тестовый товар удалён", c == 200)

print(f"\nИтог: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
