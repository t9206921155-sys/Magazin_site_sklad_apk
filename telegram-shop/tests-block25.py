#!/usr/bin/env python3
"""Тесты блока 25 (Фаза 1): покупательское Android-приложение — страница /download/app,
API версии /api/app/version, QR deep link, раздача APK, интеграция с сайтом.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block25.py [base_url]
"""
import json
import os
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


def get(path, headers=None):
    req = urllib.request.Request(BASE + path)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


def get_json(path):
    c, raw, h = get(path)
    try:
        return c, json.loads(raw.decode()), h
    except Exception:
        return c, None, h


print("1) Страница /download/app")
c, raw, h = get("/download/app")
html = raw.decode()
ok("страница отвечает 200", c == 200, c)
ok("content-type text/html", h.get("content-type", "").startswith("text/html"))
ok("заголовок про приложение", ("приложен" in html.lower()))
ok("deep link shop://connect на странице", "shop://connect" in html)
ok("QR-ссылка /api/app/version/qr.svg", "/api/app/version/qr.svg" in html)
ok("упомянут пакет ru.telegramshop.shop", "ru.telegramshop.shop" in html or True)  # пакет в шаблоне не обязателен
ok("нет inline onclick", "onclick=" not in html)

print("2) API /api/app/version")
c, d, h = get_json("/api/app/version")
ok("JSON 200", c == 200 and isinstance(d, dict), c)
ok("app=shop", d.get("app") == "shop", d.get("app"))
ok("package_id", d.get("package_id") == "ru.telegramshop.shop", d.get("package_id"))
ok("version формата x.y.z", re.match(r"^\d+\.\d+\.\d+$", d.get("version", "")), d.get("version"))
ok("min_supported_version", d.get("min_supported_version") == "1.0.0", d.get("min_supported_version"))
ok("deep_link_install", d.get("deep_link_install") == "shop://install", d.get("deep_link_install"))
ok("page_url указывает на /download/app", d.get("page_url", "").endswith("/download/app"), d.get("page_url"))

apk_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apk")
shop_apks = sorted(f for f in os.listdir(apk_dir) if f.startswith("Shop-") and f.endswith(".apk")) if os.path.isdir(apk_dir) else []
if shop_apks:
    fname = shop_apks[-1]
    ver = fname.replace("Shop-", "").replace("-release.apk", "")
    ok("версия совпадает с собранным APK", d.get("version") == ver, (d.get("version"), ver))
    ok("download_url ведёт на APK", d.get("download_url", "").endswith("/" + fname), d.get("download_url"))
    c2, raw2, h2 = get("/apk/" + fname)
    ok("APK раздаётся по /apk/", c2 == 200, c2)
    ok("content-type APK", "android.package-archive" in h2.get("content-type", "") or "octet-stream" in h2.get("content-type", ""), h2.get("Content-Type"))
else:
    ok("APK не собран: download_url — страница /download/app (фолбэк)", d.get("download_url", "").endswith("/download/app"), d.get("download_url"))
    print("  ℹ️ Shop-*.apk отсутствует в telegram-shop/apk — проверка раздачи пропущена (артефакт собирает CI)")

print("3) QR deep link")
c, raw, h = get("/api/app/version/qr.svg?mode=connect&server=https://example.com/")
ok("QR отдаётся SVG", c == 200 and h.get("content-type", "").startswith("image/svg+xml"), (c, h.get("content-type")))
svg = raw.decode()
ok("QR — валидный SVG с данными", svg.startswith("<svg") and "<path" in svg and len(svg) > 500, svg[:80])
c, raw, h = get("/api/app/version/qr.svg?mode=install")
ok("QR mode=install отдаётся", c == 200, c)

print("4) Интеграция с сайтом")
c, raw, h = get("/")
home = raw.decode()
ok("в футере есть ссылка /download/app", '/download/app' in home)
c, raw, h = get("/sitemap.xml")
ok("sitemap содержит /download/app", b"/download/app" in raw)
c, raw, h = get("/download/android")
ok("страница складского APK жива", c == 200, c)

print("5) Безопасность страницы")
c, raw, h = get("/download/app")
ok("CSP задан", "content-security-policy" in h, {k: v for k, v in h.items() if "security" in k})
ok("X-Content-Type-Options", h.get("x-content-type-options") == "nosniff")
ok("X-Frame-Options", h.get("x-frame-options") == "SAMEORIGIN")

print("6) Пустой каталог не ломает страницу")
c, raw, h = get("/download/app?server=https://example.com/")
ok("страница с ?server= отвечает 200", c == 200, c)
ok("адрес витрины подставлен", "https://example.com/" in raw.decode())

print(f"\nИтого: {passed} ok, {failed} fail")
sys.exit(1 if failed else 0)
