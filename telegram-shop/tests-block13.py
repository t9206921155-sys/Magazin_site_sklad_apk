#!/usr/bin/env python3
"""Тесты блока 13: единый storage layer — диагностика, маскирование, границы.

Проверяется по живому серверу:
- секреты (Yandex Disk OAuth, S3 secret, Supabase service key, MySQL password)
  НИКОГДА не возвращаются клиенту в /api/warehouse/settings (только «•••»);
- сохранение настроек с «•••» не затирает реальные секреты;
- /api/warehouse/cloud/config-check честно перечисляет недостающие поля
  и не делает сетевых вызовов;
- /api/warehouse/cloud/providers показывает режимы и выбранный провайдер;
- /api/warehouse/direct/config не отдаёт service-key;
- /api/warehouse/cloud/test: ненастроенный провайдер даёт понятную ошибку.

Офлайн-контракты провайдеров — в tests-storage-contracts.py.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block13.py [base_url]
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
passed = failed = 0

SECRET_YD = "YD-OAUTH-TOKEN-SECRET-13"
SECRET_S3 = "S3-SECRET-KEY-SECRET-13"
SECRET_SB = "SUPABASE-SERVICE-KEY-13"


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
        with urllib.request.urlopen(req, timeout=30) as r:
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
c, tok = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
assert c == 200, f"вход не удался: {c} {tok}"
HA = {"X-WH-Token": tok["token"]}

c, original = call("GET", "/api/warehouse/settings", None, HA)
assert c == 200, f"настройки недоступны: {c}"
ORIGINAL_CLOUD = dict(original.get("cloud") or {})

try:
    print("1) Маскирование секретов в GET /api/warehouse/settings")
    test_cloud = {"db_mode": "vps", "photo_provider": "s3", "s3_endpoint": "",
                  "yandex_disk_token": SECRET_YD, "s3_secret_key": SECRET_S3,
                  "key": SECRET_SB}
    c, r = call("PUT", "/api/warehouse/settings", {"cloud": test_cloud}, HA)
    ok("настройки сохранены", c == 200, (c, r))

    c, s = call("GET", "/api/warehouse/settings", None, HA)
    ok("GET отвечает", c == 200, c)
    cloud = s.get("cloud") or {}
    ok("yandex_disk_token маскирован", cloud.get("yandex_disk_token") == "\u2022\u2022\u2022", cloud.get("yandex_disk_token"))
    ok("s3_secret_key маскирован", cloud.get("s3_secret_key") == "\u2022\u2022\u2022", cloud.get("s3_secret_key"))
    raw = json.dumps(s, ensure_ascii=False)
    ok("YD-токен не встречается в ответе", SECRET_YD not in raw)
    ok("S3 secret не встречается в ответе", SECRET_S3 not in raw)
    ok("Supabase service key не встречается в ответе", SECRET_SB not in raw)

    print("1b) Allowlist: неизвестные поля отбрасываются при сохранении")
    c, r = call("PUT", "/api/warehouse/settings",
                {"cloud": {"supabase_key": "LEAK-UNKNOWN-13", "bucket": "test-bucket-13"}}, HA)
    ok("PUT с неизвестным полем прошёл", c == 200, (c, r))
    c, s = call("GET", "/api/warehouse/settings", None, HA)
    raw = json.dumps(s, ensure_ascii=False)
    sb_leftover = (s.get("cloud") or {}).get("supabase_key")
    ok("значение неизвестного secret-поля не сохраняется и маскируется",
       "LEAK-UNKNOWN-13" not in raw and sb_leftover in ("", "•••", None), sb_leftover)
    ok("легитимные поля при этом сохранились",
       (s.get("cloud") or {}).get("bucket") == "test-bucket-13", (s.get("cloud") or {}).get("bucket"))

    print("2) Сохранение с «•••» не затирает секреты")
    masked_back = dict(cloud)  # пришло из GET с «•••»
    masked_back["bucket"] = "test-bucket-13"
    masked_back["s3_access_key"] = "AKIA-TEST-13"
    c, r = call("PUT", "/api/warehouse/settings", {"cloud": masked_back}, HA)
    ok("сохранение с масками прошло", c == 200, (c, r))
    c, s2 = call("GET", "/api/warehouse/settings", None, HA)
    cloud2 = s2.get("cloud") or {}
    ok("маска на месте после перечитывания", cloud2.get("yandex_disk_token") == "\u2022\u2022\u2022" and cloud2.get("s3_secret_key") == "\u2022\u2022\u2022", cloud2)
    ok("обычные поля сохранились", cloud2.get("bucket") == "test-bucket-13" and cloud2.get("s3_access_key") == "AKIA-TEST-13", cloud2)

    print("3) config-check: валидация без сети")
    c, cc = call("GET", "/api/warehouse/cloud/config-check", None, HA)
    ok("config-check отвечает", c == 200 and "ok" in cc, cc)
    ok("конфиг полон → ok", cc.get("ok") is True, cc.get("missing"))
    ok("режим определён", cc.get("database_mode") == "vps" and cc.get("photo_provider") == "s3", cc)
    # уносим обязательные поля → проверяем честный список недостающего
    c, r = call("PUT", "/api/warehouse/settings",
                {"cloud": {"s3_access_key": "", "bucket": ""}}, HA)
    c, cc = call("GET", "/api/warehouse/cloud/config-check", None, HA)
    ok("пустые обязательные → ok=False", cc.get("ok") is False, cc)
    ok("missing перечисляет s3_access_key и bucket",
       "s3_access_key" in (cc.get("missing") or []) and "bucket" in (cc.get("missing") or []), cc.get("missing"))

    print("4) providers и direct/config")
    c, pr = call("GET", "/api/warehouse/cloud/providers", None, HA)
    ok("providers: список режимов", c == 200 and "vps" in (pr.get("database") or []) and "s3" in (pr.get("photos") or []), pr)
    ok("providers: выбран vps+s3", (pr.get("selected") or {}).get("database") == "vps" and (pr.get("selected") or {}).get("photos") == "s3", pr.get("selected"))
    c, dc = call("GET", "/api/warehouse/direct/config", None, HA)
    ok("direct/config: вне direct-режима выключен", c == 200 and dc.get("enabled") is False, dc)
    ok("direct/config: нет service key", SECRET_SB not in json.dumps(dc), dc)

    print("5) cloud/test: ненастроенный провайдер → понятная ошибка")
    c, t = call("POST", "/api/warehouse/cloud/test", None, HA)
    ok("cloud/test отвечает", c == 200 and "ok" in t, (c, t))
    ok("S3 без endpoint: ok=False с ошибкой",
       (t.get("storage") or {}).get("ok") is False and (t.get("storage") or {}).get("error"), t.get("storage"))
    ok("vps-база: ok=True", (t.get("database") or {}).get("ok") is True, t.get("database"))
    raw_t = json.dumps(t, ensure_ascii=False)
    ok("в диагностике нет секретов", SECRET_S3 not in raw_t and SECRET_YD not in raw_t and SECRET_SB not in raw_t)

    print("6) MySQL-режим в config-check")
    c, r = call("PUT", "/api/warehouse/settings", {"cloud": {"db_mode": "mysql", "mysql_host": "", "photo_provider": "s3", "s3_access_key": "AKIA-TEST-13", "bucket": "test-bucket-13"}}, HA)
    c, cc = call("GET", "/api/warehouse/cloud/config-check", None, HA)
    ok("mysql без host → missing содержит mysql_host",
       cc.get("database_mode") == "mysql" and "mysql_host" in (cc.get("missing") or []), cc)
finally:
    print("7) Восстановление настроек")
    c, r = call("PUT", "/api/warehouse/settings", {"cloud": ORIGINAL_CLOUD}, HA)
    ok("настройки восстановлены", c == 200, (c, r))
    c, s = call("GET", "/api/warehouse/settings", None, HA)
    after = s.get("cloud") or {}
    ok("режим совпадает с исходным",
       (after.get("db_mode") or "vps") == (ORIGINAL_CLOUD.get("db_mode") or "vps"),
       (after.get("db_mode"), ORIGINAL_CLOUD.get("db_mode")))
    for f in ("bucket", "s3_preset", "supabase_table", "supabase_schema"):
        ok(f"поле {f} восстановлено", after.get(f) == ORIGINAL_CLOUD.get(f),
           (after.get(f), ORIGINAL_CLOUD.get(f)))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
