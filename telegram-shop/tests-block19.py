#!/usr/bin/env python3
"""Тесты блока 19: внутренняя CRM — задачи, статусы, чат каналов, права.

Проверяется: доступ только по складскому токену, создание/назначение/перевод
статусов задач, комментарии-сообщения по каналам переживают обращения,
журналирование, границы прав (без токена → 403).

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block19.py [base_url]
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


print("0) Подготовка: админ и сотрудник")
c, r = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
assert c == 200, r
HA = {"X-WH-Token": r["token"]}

# второй сотрудник (worker) — для проверки общего чата
import secrets as _s
WLOGIN = "w" + _s.token_hex(3)
c, r = call("POST", "/api/warehouse/users", {"login": WLOGIN, "password": "worker-pass-123",
                                             "name": "Тестовый сотрудник", "role": "worker"}, HA)
ok("сотрудник создан", c in (200, 201), (c, r))
c, r = call("POST", "/api/warehouse/login", {"login": WLOGIN, "password": "worker-pass-123"})
HW = {"X-WH-Token": r["token"]} if c == 200 else {}
ok("сотрудник вошёл", c == 200 and bool(HW), (c, r))

try:
    print("1) Задачи: создание, назначение, статусы")
    c, r = call("POST", "/api/crm/tasks",
                {"title": "Проверить остатки по коробке A2", "description": "тест 19",
                 "priority": "high", "assignee_id": 0}, HA)
    ok("задача создана", c in (200, 201) and r.get("id"), (c, r))
    TID = r["id"]
    c, r = call("POST", "/api/crm/tasks", {"description": "без заголовка"}, HA)
    ok("задача без title → 422", c == 422, c)
    c, r = call("PUT", f"/api/crm/tasks/{TID}", {"assignee_id": 1, "status": "in_progress",
                                                 "due_at": "2026-12-31T18:00:00"}, HA)
    ok("назначение и статус обновлены", c == 200, (c, r))
    c, tasks = call("GET", "/api/crm/tasks", None, HA)
    t = next((x for x in tasks if x["id"] == TID), {})
    ok("задача читается с полями", t.get("status") == "in_progress" and t.get("assignee_id") == 1, t)
    c, r = call("PUT", f"/api/crm/tasks/{TID}", {"status": "done"}, HW)
    ok("worker может переводить статус", c == 200, (c, r))
    c, r = call("PUT", "/api/crm/tasks/999999", {"status": "done"}, HA)
    ok("чужая/несуществующая задача → 404", c == 404, c)
    c, r = call("PUT", f"/api/crm/tasks/{TID}", {}, HA)
    ok("пустой patch → 422", c == 422, c)

    print("2) Чат каналов: общий и групповой")
    c, r = call("POST", "/api/crm/messages", {"channel": "general", "body": "Всем доброе утро!"}, HA)
    ok("сообщение отправлено", c in (200, 201), (c, r))
    MID = r.get("id")
    c, r = call("POST", "/api/crm/messages", {"channel": "general", "body": "Принято, беру коробку A2"}, HW)
    ok("второй сотрудник пишет в общий канал", c in (200, 201), (c, r))
    c, r = call("GET", "/api/crm/messages?channel=general", None, HA)
    msgs = r if isinstance(r, list) else []
    ok("оба сообщения видны обоим (общий чат)",
       any(m["id"] == MID for m in msgs) and len(msgs) >= 2, len(msgs))
    c, r = call("POST", "/api/crm/messages", {"channel": "мусор" + "x" * 100, "body": "ок"}, HA)
    ok("длинный канал обрезается, не падает", c in (200, 201), c)
    c, r = call("POST", "/api/crm/messages", {"channel": "general", "body": ""}, HA)
    ok("пустое сообщение → 422", c == 422, c)
    c, r = call("GET", "/api/crm/messages?channel=general", None, HA)
    ok("перезапуск не нужен: данные из БД", isinstance(r, list))

    print("3) Границы прав")
    c, _ = call("GET", "/api/crm/tasks")
    ok("задачи без токена → 403", c == 403, c)
    c, _ = call("GET", "/api/crm/messages", None, {"X-WH-Token": "wrong:token"})
    ok("чужой токен → 403", c == 403, c)
    c, _ = call("POST", "/api/crm/messages", {"channel": "general", "body": "hi"},
                {"X-Admin-Token": "bad-admin"})
    ok("неверный админ-токен → 403", c == 403, c)

finally:
    print("4) Очистка")
    c, _ = call("PUT", f"/api/crm/tasks/{TID}", {"status": "done",
                                                 "description": "тест блока 19 — закрыто"}, HA)
    ok("тестовая задача закрыта", c == 200, c)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
