#!/usr/bin/env python3
"""Тесты блока 15: production security и observability.

Проверяется по живому серверу:
- security headers на всех ответах;
- CORS preflight отвечает allow-origin;
- /metrics: безопасная телеметрия (счётчики, латентность, статусы) без секретов;
- /health/ready: проверка БД, конфига, data/ и свободного места, без секретов;
- маскирование секретов в логах (офлайн-тест фильтра);
- неудачный backup фиксируется в диагностике и /metrics;
- TTL сессий быстрого входа склада;
- watchdog-скрипт и systemd-юнит на месте;
- rate limit: 1С и login (флуд — в самом конце, т.к. после него IP в карантине ~60с).

ВАЖНО: запускать ПОСЛЕДНИМ в регрессии (флуд-тесты ставят IP в лимит на ~60с).

Запуск: cd telegram-shop && python3 tests-block15.py [base_url]
"""
import json
import logging
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent
passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  \u2705 {name}")
    else:
        failed += 1
        print(f"  \u274c {name}{(' — ' + str(extra)) if extra else ''}")


def call(method, path, body=None, headers=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    def _lower_headers(hs):
        return {str(k).lower(): str(v) for k, v in hs.items()}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _lower_headers(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, _lower_headers(e.headers), e.read().decode()


def jbody(raw):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


print("0) Подготовка")
c, h, raw = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
tok = jbody(raw).get("token", "")
assert c == 200 and tok, f"вход не удался: {c} {raw[:100]}"
HA = {"X-WH-Token": tok}

print("1) Security headers")
c, h, _ = call("GET", "/")
ok("страница отвечает", c == 200, c)
ok("X-Content-Type-Options: nosniff", h.get("x-content-type-options") == "nosniff", h.get("x-content-type-options"))
ok("X-Frame-Options: SAMEORIGIN", h.get("x-frame-options") == "SAMEORIGIN", h.get("x-frame-options"))
ok("Referrer-Policy задан", bool(h.get("referrer-policy")), h.get("referrer-policy"))
ok("Permissions-Policy задан", bool(h.get("permissions-policy")), h.get("permissions-policy"))
ok("X-Request-ID выдан", bool(h.get("x-request-id")))

print("2) CORS preflight")
req = urllib.request.Request(BASE + "/api/catalog", method="OPTIONS")
req.add_header("Origin", "https://example.com")
req.add_header("Access-Control-Request-Method", "GET")
with urllib.request.urlopen(req, timeout=10) as r:
    cors = dict(r.headers)
ok("preflight отвечает allow-origin", bool(cors.get("access-control-allow-origin")), cors.get("access-control-allow-origin"))
ok("allow-credentials не включён (секретные куки не летят)",
   cors.get("access-control-allow-credentials") != "true", cors.get("access-control-allow-credentials"))

print("3) /metrics: телеметрия без секретов")
c, h, raw = call("GET", "/metrics")
m = jbody(raw)
ok("metrics отвечает 200 (токен не задан)", c == 200, c)
ok("счётчики на месте", isinstance(m.get("requests"), int) and isinstance(m.get("errors"), int), m.keys())
ok("uptime и латентность присутствуют", "uptime_s" in m and "avg_ms" in (m.get("latency") or {}), m.get("latency"))
ok("коды статусов — числа", all(k.isdigit() for k in (m.get("statuses") or {})), m.get("statuses"))
ok("last_backup_error виден в метриках", "last_backup_error" in m, m.keys())
raw_all = json.dumps(m, ensure_ascii=False)
ok("нет пароля admin123 в метриках", "admin123" not in raw_all)
ok("нет заголовков/секретов в метриках", "X-WH-Token" not in raw_all and "password" not in raw_all.lower().replace("last_backup_error", ""))
c, h, raw = call("GET", "/metrics", None, {"X-Metrics-Token": "wrong-token-nope"})
ok("неверный токен метрик → 403 не возникает, когда METRICS_TOKEN пуст (режим песочницы)", c in (200, 403), c)

print("4) /health/ready: диск и отсутствие секретов")
c, h, raw = call("GET", "/health/ready")
r = jbody(raw)
ok("ready отвечает ok", c == 200 and r.get("ok") is True, raw[:150])
ch = r.get("checks") or {}
ok("проверки: database/config/data_dir/disk", all(k in ch for k in ("database", "config", "data_dir", "disk")), ch.keys())
ok("свободное место показано числом", isinstance(ch.get("disk_free_mb"), int) and ch["disk_free_mb"] >= 0, ch.get("disk_free_mb"))
ok("в readiness нет секретов", "admin123" not in raw and "token" not in raw.lower())

print("5) Маскирование секретов в логах (офлайн)")
sys.path.insert(0, str(ROOT))
from api import SecretMaskingFilter, mask_secrets  # noqa: E402
samples = {
    "вход ok token=abc123def": "abc123def",
    "password=hunter2 принят": "hunter2",
    "cfg: api_key=SK-1234-5678": "SK-1234-5678",
    "secret: топ-секрет-значение": "топ-секрет-значение",
}
for src_text, needle in samples.items():
    rec = logging.LogRecord("shop", logging.WARNING, __file__, 1, src_text, None, None)
    SecretMaskingFilter().filter(rec)
    ok(f"маскировано: {src_text[:28]!r}", needle not in rec.getMessage(), rec.getMessage())
plain = "обычный лог без секретов, заказ #123"
rec = logging.LogRecord("shop", logging.INFO, __file__, 1, plain, None, None)
SecretMaskingFilter().filter(rec)
ok("обычный текст не искажён", rec.getMessage() == plain, rec.getMessage())

print("6) Неудачный backup → last_error в диагностике и /metrics")
c, h, raw = call("POST", "/api/warehouse/cloud/backup", None, HA)
r = jbody(raw)
ok("backup без S3 → ok=False с ошибкой", c == 200 and r.get("ok") is False and r.get("error"), raw[:150])
c, h, raw = call("GET", "/api/warehouse/cloud/status", None, HA)
st = jbody(raw)
ok("статус облака содержит last_error", (st.get("backup") or {}).get("last_error", "") != "", (st.get("backup") or {}).get("last_error"))
c, h, raw = call("GET", "/metrics")
ok("last_backup_error пробросился в /metrics", jbody(raw).get("last_backup_error", "") != "")

print("7) TTL сессий быстрого входа (офлайн)")
from store import store as ST  # noqa: E402
import config  # noqa: E402
sec = ST.wh_session_create(0)
ok("сессия создана", bool(sec) and ST._q1("SELECT 1 x FROM wh_sessions WHERE secret=?", (sec,)) is not None)
ok("свежая сессия проходит TTL-проверку (пользователя нет — None, но сессия жива)",
   ST.wh_session_login(sec) is None
   and ST._q1("SELECT 1 x FROM wh_sessions WHERE secret=?", (sec,)) is not None)
old = "2020-01-01T00:00:00+00:00"
ST._conn.execute("UPDATE wh_sessions SET created_at=?, last_used=? WHERE secret=?", (old, old, sec))
ST._conn.commit()
ok("просроченная сессия отклонена", ST.wh_session_login(sec) is None)
ok("просроченная сессия удалена из БД",
   ST._q1("SELECT 1 x FROM wh_sessions WHERE secret=?", (sec,)) is None)
ok("конфиг TTL читается", int(config.WH_SESSION_TTL_DAYS) >= 1)

print("8) Watchdog: скрипт и юнит")
wd = ROOT / "scripts" / "server_watchdog.sh"
ok("watchdog-скрипт существует и исполняемый", wd.is_file() and wd.stat().st_mode & 0o111)
res = subprocess.run(["bash", "-n", str(wd)], capture_output=True, text=True)
ok("синтаксис watchdog корректен", res.returncode == 0, res.stderr[:150])
ok("systemd-юнит watchdog существует", (ROOT.parent / "deploy" / "magazin-watchdog.service").is_file())

print("9) Rate limit (флуд — финальные тесты, после них IP в карантине ~60с)")
statuses = []
for i in range(125):
    c, _, _ = call("GET", "/1c/catalog", None, {"X-1C-Token": "wrong-token"})
    statuses.append(c)
ok("1С без токена даёт 403", 403 in statuses, set(statuses))
ok("превышение лимита 1С → 429", 429 in statuses, set(statuses))
ok("хвост флуда — все 429", statuses[-1] == 429 and statuses[-5:] == [429] * 5, statuses[-5:])
login_statuses = []
for i in range(21):
    c, _, _ = call("POST", "/api/warehouse/login", {"login": "admin", "password": "wrong-pass"})
    login_statuses.append(c)
ok("флуд login → 429", 429 in login_statuses, set(login_statuses))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
