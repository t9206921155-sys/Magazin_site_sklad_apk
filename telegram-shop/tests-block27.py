#!/usr/bin/env python3
"""Тесты блока 27: CSP-закалка — вынос inline-JS и Content-Security-Policy.

Проверяется:
- строгий CSP (script-src 'self', без unsafe-inline) на публичных SSR-страницах;
- в HTML публичных страниц не осталось inline <script> и onclick-обработчиков;
- внутренние инструменты (Mini App, склад, админка, CRM, кабинет, SPA /shop)
  получают политику в режиме Report-Only и продолжают работать;
- JSON-LD (данные для поисковиков) сохраняется на страницах товара.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block27.py [base_url]
"""
import json
import re
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


def get(path, headers=None, body=None, method="GET"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I)


def csp_of(h):
    return h.get("content-security-policy") or ""


def csp_ro_of(h):
    return h.get("content-security-policy-report-only") or ""


def script_src(policy):
    m = re.search(r"script-src([^;]*)", policy or "")
    return m.group(1).strip() if m else ""


print("0) Подготовка: товар и продавец")
c, raw, _ = get("/api/warehouse/login", body={"login": "admin", "password": "admin123"}, method="POST")
assert c == 200, f"вход не удался: {c} {raw[:200]}"
HA = {"X-WH-Token": json.loads(raw.decode())["token"]}
c, raw, _ = get("/api/warehouse/products", headers=HA, body={"name": "Б27CSP товар", "stock": 3, "price": 900}, method="POST")
assert c == 201, f"товар не создан: {c} {raw[:200]}"
PID = json.loads(raw.decode())["id"]
import time
SLUG = "b27-csp-" + str(int(time.time()))
c, s, _ = get("/api/seller/register", body={"store_name": "Б27 Витрина", "phone": "+7999000" + str(int(time.time()))[-4:], "slug": SLUG}, method="POST")
SELLER_OK = c in (200, 201)

print("1) Строгий CSP на публичных страницах")
STRICT_PAGES = ["/", "/catalog", "/favorites", "/become-seller", "/blog", "/download/android", "/download/app", "/privacy"]
for path in STRICT_PAGES:
    c, raw, h = get(path)
    policy = csp_of(h)
    ok(f"{path}: 200", c == 200, c)
    ok(f"{path}: CSP задан", bool(policy), dict((k, v) for k, v in h.items() if "Content-Security" in k))
    ok(f"{path}: script-src 'self'", "self" in script_src(policy) if policy else False, script_src(policy))
    ok(f"{path}: без unsafe-inline в script-src", "unsafe-inline" not in script_src(policy), script_src(policy))

print("2) В HTML публичных страниц нет inline-скриптов и onclick")
for path in STRICT_PAGES + [f"/p/{PID}"]:
    c, raw, h = get(path)
    html = raw.decode()
    bad = [m.group(0) for m in INLINE_SCRIPT.finditer(html) if "application/ld+json" not in m.group(0)]
    ok(f"{path}: нет inline <script>", not bad, bad[:2])
    ok(f"{path}: нет onclick=", "onclick=" not in html)

print("3) Страница товара: JS-файлы и JSON-LD на месте")
c, raw, h = get(f"/p/{PID}")
html = raw.decode()
ok("подключён product-page.js", "/site/js/product-page.js" in html)
ok("подключён page-common.js", "/site/js/page-common.js" in html)
ok("data-product-id проставлен", f'data-product-id="{PID}"' in html)
ok("JSON-LD сохранён", "application/ld+json" in html)
ok("chat-кнопки без onclick", 'id="chat-close-btn"' in html or "chat-panel" not in html)

print("4) Внешние JS-файлы отдаются")
for js in ("/site/js/page-common.js", "/site/js/product-page.js", "/site/js/home-page.js",
           "/site/js/catalog-page.js", "/site/js/favorites-page.js", "/site/js/become-seller.js",
           "/site/js/android-download.js", "/site/js/android-rustore.js", "/site/js/spa-bootstrap.js",
           "/site/js/app-download.js"):
    c, raw, h = get(js)
    ok(f"{js}", c == 200 and h.get("content-type", "").startswith(("application/javascript", "text/javascript")), (c, h.get("content-type")))

print("5) Внутренние инструменты: только Report-Only")
RELAXED_PAGES = ["/shop", "/app", "/warehouse/", "/admin/", "/crm/"]
for path in RELAXED_PAGES:
    c, raw, h = get(path)
    ok(f"{path}: 200", c == 200, c)
    ok(f"{path}: enforce-CSP НЕ ставится", not csp_of(h), csp_of(h))
    ok(f"{path}: Report-Only задан", bool(csp_ro_of(h)))

print("6) Публичная витрина продавца — строгий CSP")
if SELLER_OK:
    c, raw, h = get("/seller/" + SLUG)
    ok("витрина 200", c == 200, c)
    ok("витрина: CSP строгий", "self" in script_src(csp_of(h)), csp_of(h))
else:
    c, raw, h = get("/seller/" + SLUG)
    ok("витрина отвечает", c == 200, c)

print("7) SPA-страница /shop — shell без inline-скриптов")
c, raw, h = get("/shop")
html = raw.decode()
bad = [m.group(0) for m in INLINE_SCRIPT.finditer(html)]
ok("/shop: нет inline <script> после выноса bootstrap", not bad, bad[:2])
ok("/shop: подключён spa-bootstrap.js", "/site/js/spa-bootstrap.js" in html)

print("8) API не тронуты")
c, raw, h = get("/api/catalog")
ok("/api/catalog 200", c == 200, c)
c, raw, h = get("/health/ready")
ok("/health/ready 200", c == 200 and b'"ok":true' in raw, (c, raw[:80]))

print(f"\nИтого: {passed} ok, {failed} fail")
sys.exit(1 if failed else 0)
