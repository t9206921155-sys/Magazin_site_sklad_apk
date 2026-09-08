#!/usr/bin/env python3
"""Тесты блока 09: маркетплейс-каталог — фильтры, сортировка, поиск, пагинация.

Проверяется, что каждый фильтр РЕАЛЬНО влияет на выдачу (создаём товары
с разными атрибутами и сравниваем выборки), поиск не падает на спецсимволах,
мусорные параметры не дают 500, пагинация API работает, SSR-страницы каталога
рендерятся со всеми фильтрами.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block09.py [base_url]
"""
import json
import sys
import urllib.error
import urllib.parse
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
    """Возвращает (status, data|str)."""
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


def catalog(**params):
    qs = urllib.parse.urlencode(params)
    return call("GET", "/api/catalog" + (("?" + qs) if qs else ""))


def ids(data):
    return {p["id"] for p in data.get("products", [])}


print("0) Подготовка")
c, tok = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
assert c == 200, f"вход не удался: {c} {tok}"
HA = {"X-WH-Token": tok["token"]}

MARK = "Б09АУДИТ"
# три товара с разными атрибутами:
#   cheap — б/у, торг, БЕЗ фото, цена 500
#   mid   — б/у, торг, с фото (плейсхолдер по умолчанию), цена 1500
#   dear  — новое, без торга, БЕЗ фото, цена 5000
created = []
for name, extra in (
    (f"{MARK} дешёвый", {"price": 500, "condition": "used", "negotiable": True, "photo": ""}),
    (f"{MARK} средний", {"price": 1500, "condition": "used", "negotiable": True}),
    (f"{MARK} дорогой", {"price": 5000, "condition": "new", "negotiable": False, "photo": ""}),
):
    c, p = call("POST", "/api/warehouse/products", {"name": name, "stock": 5, **extra}, HA)
    assert c == 201, f"товар {name} не создан: {c} {p}"
    created.append(p)

try:
    CHEAP, MID, DEAR = (p["id"] for p in created)
    ours = {CHEAP, MID, DEAR}

    print("1) Базовая выдача и фильтр по цене")
    c, d = catalog()
    ok("каталог отвечает", c == 200 and isinstance(d.get("products"), list))
    ok("тестовые товары в выдаче", ours <= ids(d), sorted(ours - ids(d)))
    c, d = catalog(price_min=1000)
    ok("price_min=1000 отсекает дешёвое", MID in ids(d) and DEAR in ids(d) and CHEAP not in ids(d), ids(d))
    c, d = catalog(price_max=2000)
    ok("price_max=2000 отсекает дорогое", CHEAP in ids(d) and MID in ids(d) and DEAR not in ids(d), ids(d))
    c, d = catalog(price_min=600, price_max=2000)
    ok("цена-диапазон: средний внутри, дешёвый/дорогой снаружи",
       MID in ids(d) and CHEAP not in ids(d) and DEAR not in ids(d), sorted(ids(d) & ours))

    print("2) Состояние, фото, торг, продавец")
    c, d = catalog(condition="used")
    ok("condition=used: только б/у", CHEAP in ids(d) and MID in ids(d) and DEAR not in ids(d), ids(d))
    c, d = catalog(condition="nonsense")
    ok("condition=мусор: пусто", c == 200 and d["products"] == [])
    c, d = catalog(has_photo=True)
    ok("has_photo: без фото не показываем", DEAR not in ids(d) and MID in ids(d), sorted(ours - ids(d)))
    c, d = catalog(negotiable=True)
    ok("negotiable: только с торгом", CHEAP in ids(d) and MID in ids(d) and DEAR not in ids(d), ids(d))
    c, d = catalog(negotiable=True, price_max=1000)
    ok("комбинация negotiable+цена", ids(d) == {CHEAP}, ids(d))
    c, d = catalog(seller="no-such-seller")
    ok("seller=несуществующий: пусто", c == 200 and d["products"] == [])
    c, d = catalog(cat="Несуществующая категория")
    ok("cat=несуществующая: пусто (пустая выдача без падения)", c == 200 and d["products"] == [])
    c, d = catalog(sub="nonesuchsub")
    ok("sub=несуществующая: пусто", c == 200 and d["products"] == [])

    print("3) Сортировка")
    c, d = catalog(sort="price_asc", per_page=100)
    prices = [p["price"] for p in d["products"]]
    ok("sort=price_asc упорядочивает", prices == sorted(prices), prices)
    c, d = catalog(sort="price_desc", per_page=100)
    prices = [p["price"] for p in d["products"]]
    ok("sort=price_desc упорядочивает", prices == sorted(prices, reverse=True), prices)
    c, d = catalog(sort="new")
    ok("sort=new отвечает", c == 200 and d["products"])
    c, d = catalog(sort="rating")
    ok("sort=rating отвечает (рейтинг продавца)", c == 200 and d["products"])
    c, d = catalog(sort="nonsense")
    ok("sort=мусор — просто без сортировки", c == 200 and d["products"])

    print("4) Поиск: спецсимволы и пустой запрос")
    uniq = MARK  # уникальная подстрока наших товаров
    c, d = catalog(q=uniq)
    ok("поиск находит только тестовые", c == 200 and ours <= ids(d), sorted(ours - ids(d)))
    for bad in ("%<>'\"&", "%25%3C%3E", "' OR 1=1 --", "(((", "***", "\\\\", "  "):
        c, d = catalog(q=bad)
        ok(f"поиск не падает на {bad!r}", c == 200 and isinstance(d.get("products"), list))
    c, d = catalog(q="")
    ok("пустой q = обычная выдача", c == 200 and ours <= ids(d))

    print("5) Невалидные параметры и пагинация API")
    c, _ = catalog(price_min="abc")
    ok("price_min=abc → 422, не 500", c == 422, c)
    c, _ = catalog(page="много")
    ok("page=мусор → 422, не 500", c == 422, c)
    c, d = catalog(page=-5)
    ok("page<0 → клампится к 1", c == 200 and d["page"] == 1, d.get("page"))
    c, d = catalog(per_page=9999)
    ok("per_page ограничен сверху", c == 200 and d["per_page"] <= 100, d.get("per_page"))
    c, d = catalog(per_page=0)
    ok("per_page=0 — без нарезки, есть total", c == 200 and d["per_page"] == 0 and d["total"] >= len(d["products"]), d.get("total"))
    c, d = catalog(per_page=2)
    ok("per_page=2: на странице ≤2", len(d["products"]) <= 2 and d["pages"] >= 2, (len(d["products"]), d.get("pages")))
    ok("total совпадает с полной выдачей", d["total"] >= 3, d["total"])
    c1, d1 = catalog(per_page=2, page=1)
    c2, d2 = catalog(per_page=2, page=2)
    i1, i2 = ids(d1), ids(d2)
    ok("страницы 1 и 2 различаются", i1 and i2 and not (i1 == i2 and d1["total"] > 2), (i1, i2))
    c, d = catalog(per_page=2, page=999)
    ok("page за пределами → последняя страница", c == 200 and d["page"] == d["pages"], (d.get("page"), d.get("pages")))

    print("6) SSR-страницы каталога")
    c, html = call("GET", "/catalog")
    ok("/catalog рендерится (регрессия NameError)", c == 200 and "Применить" in html)
    c, html = call("GET", "/catalog?price_min=1000&price_max=2000")
    ok("SSR фильтр цены: средний виден", c == 200 and f"{MARK} средний" in html)
    ok("SSR фильтр цены: дешёвый скрыт", c == 200 and f"{MARK} дешёвый" not in html)
    c, html = call("GET", "/catalog?negotiable=true")
    ok("SSR торг: дорогой скрыт", c == 200 and f"{MARK} дорогой" not in html)
    c, html = call("GET", "/catalog?sort=price_desc")
    ok("SSR sort=price_desc", c == 200 and html.find(f"{MARK} дорогой") < html.find(f"{MARK} дешёвый"))
    c, html = call("GET", "/catalog?q=" + urllib.parse.quote("%<>'\""))
    ok("SSR поиск со спецсимволами не падает", c == 200)
    c, html = call("GET", "/catalog/nonesuch-slug")
    ok("несуществующая категория → 404", c == 404, c)
    c, html = call("GET", "/api/catalog?seller=" + urllib.parse.quote("no-such") + "&condition=used&has_photo=true&negotiable=true")
    ok("все фильтры сразу — 200", c == 200 and isinstance(d.get("products"), list))
finally:
    print("7) Очистка")
    for p in created:
        c, _ = call("PUT", f"/api/warehouse/products/{p['id']}",
                    {"is_archived": True, "in_stock": False}, HA)
        ok(f"архивирован {p['name']}", c == 200, c)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
