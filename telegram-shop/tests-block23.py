#!/usr/bin/env python3
"""Тесты блока 23: Content Hub и очередь контента.

Проверяется полный жизненный цикл content_jobs:
создание из товара → claim → callback результата (HMAC опционально) → review
→ approve/reject → retry → cancel; локальный fallback-слайдшоу без ИИ
(ffmpeg через media.py) переводит задачу в review с готовым роликом.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block23.py [base_url]
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
passed = failed = 0
MARK = f"B23-{int(time.time()) % 100000}"


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
        with urllib.request.urlopen(req, timeout=60) as r:
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


print("0) Подготовка")
c, r = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
assert c == 200, r
HA = {"X-WH-Token": r["token"]}
c, p = call("POST", "/api/warehouse/products",
            {"name": f"{MARK} товар для ролика", "price": 777, "stock": 3}, HA)
assert c == 201, (c, p)
PID = p["id"]

created = []
try:
    print("1) Создание задачи из товара")
    c, r = call("POST", "/api/content/jobs", {"product_id": PID, "provider": "external"}, HA)
    ok("задача создана в очереди", c in (200, 201) and r.get("id"), (c, r))
    J1 = r["id"]
    created.append(J1)
    c, r = call("GET", f"/api/content/prompt/{PID}", None, HA)
    ok("промпт из объявления доступен", c == 200 and bool(r), (c, str(r)[:120]))

    print("2) Claim → callback → review → approve")
    c, r = call("POST", f"/api/content/jobs/{J1}/claim", {"provider": "external-ai"}, HA)
    ok("задача забрана провайдером", c == 200, (c, r))
    c, r = call("POST", f"/api/content/jobs/{J1}/result",
                {"result_url": "https://cdn.example.com/video-23.mp4"}, HA)
    ok("callback с URL → review", c == 200 and r.get("status") == "review", (c, r))
    c, r = call("POST", f"/api/content/jobs/{J1}/approve", {"comment": "ок"}, HA)
    ok("approve публикует задачу", c == 200, (c, r))
    c, jobs = call("GET", "/api/content/jobs", None, HA)
    job = next((j for j in jobs if j["id"] == J1), {})
    ok("итоговый статус и результат сохранены",
       job.get("status") == "approved" and "cdn.example.com" in (job.get("result_url") or ""), job)

    print("3) Ошибка провайдера: failed, магазин работает, retry")
    c, r = call("POST", "/api/content/jobs", {"product_id": PID, "provider": "external"}, HA)
    J2 = r["id"]
    created.append(J2)
    call("POST", f"/api/content/jobs/{J2}/claim", {"provider": "external-ai"}, HA)
    c, r = call("POST", f"/api/content/jobs/{J2}/result", {"error": "provider exploded"}, HA)
    ok("callback с ошибкой → failed", c == 200, (c, r))
    c, r = call("GET", "/api/health", None)
    ok("магазин продолжает работать", c == 200, c)
    c, r = call("POST", f"/api/content/jobs/{J2}/retry", None, HA)
    ok("retry возвращает в очередь", c == 200, (c, r))

    print("4) Локальный fallback-слайдшоу без ИИ")
    c, r = call("POST", f"/api/content/jobs/{J2}/fallback", None, HA)
    ok("fallback отрендерил ролик", c == 200 and r.get("status") == "review", (c, r))
    url = r.get("result_url") or ""
    ok("ролик локальный /media/videos/*.mp4", url.startswith("/media/videos/") and url.endswith(".mp4"), url)
    c, h = call("GET", url, None) if False else (None, None)
    import urllib.request as _u
    with _u.urlopen(BASE + url, timeout=30) as resp:
        head = resp.read(16)
    ok("файл ролика существует и это MP4", head[:2] == b"\x00\x00" or b"ftyp" in resp.headers.get("Content-Type", "").encode() or resp.headers.get("Content-Type") in ("video/mp4", "application/octet-stream"), (head[:4], resp.headers.get("Content-Type")))
    c, jobs = call("GET", "/api/content/jobs", None, HA)
    jb = next((j for j in jobs if j["id"] == J2), {})
    ok("задача после fallback в review с локальным роликом",
       jb.get("status") == "review" and jb.get("provider") == "local-slideshow"
       and url in (jb.get("result_url") or ""), jb)
    c, r = call("POST", f"/api/content/jobs/{J2}/result",
                {"result_url": "/etc/passwd"}, HA)
    ok("относительный путь в колбэке отклоняется (защита)", c == 422, (c, r))

    print("5) Отмена и границы")
    c, r = call("POST", "/api/content/jobs", {"product_id": PID}, HA)
    J3 = r["id"]
    created.append(J3)
    c, r = call("POST", f"/api/content/jobs/{J3}/cancel", None, HA)
    ok("задача отменена", c == 200, (c, r))
    c, r = call("POST", f"/api/content/jobs/{J3}/claim", {"provider": "x"}, HA)
    ok("отменённую нельзя забрать", c == 409, (c, r))
    c, _ = call("POST", "/api/content/jobs", {"product_id": PID})
    ok("создание без токена → 403", c == 403, c)
    c, r = call("POST", f"/api/content/jobs/{J2}/fallback", None, {"X-WH-Token": "bad"})
    ok("fallback без токена → 403", c == 403, c)
    c, r = call("POST", "/api/content/jobs/999999/fallback", None, HA)
    ok("fallback несуществующей задачи → 404", c == 404, c)

finally:
    print("6) Очистка")
    for j in created:
        c, _ = call("POST", f"/api/content/jobs/{j}/cancel", None, HA)
    c, _ = call("PUT", f"/api/warehouse/products/{PID}", {"is_archived": True, "in_stock": False}, HA)
    ok("тестовый товар архивирован", c == 200, c)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
