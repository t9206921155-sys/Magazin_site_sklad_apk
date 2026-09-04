"""Тесты Этапа 5: обмен остатками с 1С + логика офлайн-очереди.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-stage5.py [base_url]
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


# ---- подготовка: токены
import store as st  # noqa: E402

s = st.Store()
T1C = s.settings.get("1c_token")
H1C = {"X-1C-Token": T1C}

code, tok = call("POST", "/api/warehouse/login",
                 {"login": "admin", "password": "admin123"})
assert code == 200, f"не удалось войти на склад: {code} {tok}"
HW = {"X-WH-Token": tok["token"]}

CODE = "TEST-1C-STOCK"
print("0) Подготовка тестового товара")
call("POST", "/api/warehouse/products",
     {"name": "Тест 1С остатки", "price": 100, "stock": 10,
      "sku": "T1C", "code": CODE}, HW)
st_code, listing = call("GET", "/1c/stock", None, H1C)
found = [i for i in listing.get("items", []) if i["code"] == CODE]
ok("товар создан и виден в /1c/stock", bool(found), listing)
pid = found[0]["id"] if found else None

print("1) POST /1c/stock — обновление остатка и цены")
c, r = call("POST", "/1c/stock", {"items": [{"code": CODE, "stock": 47, "price": 777}]}, H1C)
ok("ответ 200 + updated=1", c == 200 and r.get("updated") == 1, r)
_, listing = call("GET", "/1c/stock", None, H1C)
cur = [i for i in listing["items"] if i["code"] == CODE][0]
ok("остаток стал 47", cur["stock"] == 47, cur)
ok("цена стала 777", cur["price"] == 777, cur)

print("2) Название и прочие поля не затираются")
ok("имя сохранилось", cur["name"] == "Тест 1С остатки", cur)

print("3) stock=0 снимает товар с продажи")
call("POST", "/1c/stock", {"items": [{"code": CODE, "stock": 0}]}, H1C)
_, listing = call("GET", "/1c/stock", None, H1C)
cur = [i for i in listing["items"] if i["code"] == CODE][0]
ok("in_stock=False при нулевом остатке", cur["in_stock"] is False, cur)

print("4) Неизвестный код не ломает пакет")
c, r = call("POST", "/1c/stock",
            {"items": [{"code": "NO-SUCH-CODE"}, {"code": CODE, "stock": 5}]}, H1C)
ok("частичный успех", c == 200 and r.get("updated") == 1, r)
ok("неизвестный код в not_found", "NO-SUCH-CODE" in (r.get("not_found") or []), r)

print("5) Валидация и защита")
c, _ = call("POST", "/1c/stock", {"items": [{"code": CODE}]})
ok("без токена -> 403", c == 403)
c, _ = call("POST", "/1c/stock", {"items": []}, H1C)
ok("пустой items -> 422", c == 422)
c, _ = call("POST", "/1c/stock", {"x": 1}, H1C)
ok("нет ключа items -> 422", c == 422)
c, _ = call("POST", "/1c/stock", {"items": [{"code": "X"}] * 5001}, H1C)
ok("более 5000 позиций -> 413", c == 413)
c, r = call("POST", "/1c/stock",
            {"items": [{"code": CODE, "stock": "abc", "price": "xyz"}]}, H1C)
ok("нечисловые значения не роняют сервер", c == 200, r)

print("6) Остаток из 1С виден на складе")
_, wh = call("GET", f"/api/warehouse/products/{pid}", None, HW)
item = (wh.get("products") or [{}])[0] if isinstance(wh, dict) else {}
ok("склад видит обновлённый остаток", item.get("stock") == 5, item)

print("7) Существующие 1С-маршруты не сломаны")
for path in ("/1c/catalog", "/1c/orders", "/1c/stock"):
    c, _ = call("GET", path, None, H1C)
    ok(f"GET {path} -> 200", c == 200)

print("8) Service worker: стратегии кэширования")
sw = open("warehouse/sw.js", encoding="utf-8").read()
ok("API больше не cache-first", "network-first" in sw or "isApi" in sw)
ok("есть очередь офлайн-операций", "queueAdd" in sw and "flushQueue" in sw)
ok("есть Background Sync", "'sync'" in sw and "wh-sync" in sw)
ok("чувствительные ответы не кэшируются", "isSensitive" in sw)
ok("кэш оболочки и API разделены", "SHELL_CACHE" in sw and "API_CACHE" in sw)

print("\nОчистка")
if pid:
    c, _ = call("DELETE", f"/api/warehouse/products/{pid}", None, HW)
    ok("тестовый товар удалён", c == 200)

print(f"\nИтог: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
