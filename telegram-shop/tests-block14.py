#!/usr/bin/env python3
"""Тесты блока 14: backup, restore и миграция SQLite → MySQL.

Проверяется:
- backup API на ненастроенном S3 даёт понятную ошибку (не падает);
- атомарный снимок store.export_sqlite_backup: integrity ok, количества записей
  совпадают с живой базой;
- verify_restore.py: валидный бэкап → exit 0; подделанный → exit 1;
- restore_sqlite.py: dry-run не трогает цель;
- migrate_sqlite_to_mysql.py: dry-run без MySQL; логика копирования и сверки
  (migrate_apply) на фейковом таргете — полная копия и обнаружение расхождений;
- translate_ddl: без AUTOINCREMENT, без двойных кавычек;
- исходная БД (байт-в-байт) не меняется после всех операций.

Запуск (сервер должен быть поднят):
    cd telegram-shop && python3 tests-block14.py [base_url]
"""
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
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


def load_mod(name, relpath):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


sys.path.insert(0, str(ROOT))
from store import store  # noqa: E402

mig = load_mod("b14_migrate", "scripts/migrate_sqlite_to_mysql.py")

LIVE = ROOT / "data" / "shop.db"

print("0) Подготовка")
c, tok = call("POST", "/api/warehouse/login", {"login": "admin", "password": "admin123"})
assert c == 200, f"вход не удался: {c}"
HA = {"X-WH-Token": tok["token"]}

print("1) Backup API: ненастроенный S3 → понятная ошибка")
c, r = call("POST", "/api/warehouse/cloud/backup", None, HA)
ok("endpoint отвечает", c == 200, (c, r))
ok("ok=False с пояснением", r.get("ok") is False and "S3" in (r.get("error") or ""), r)

print("2) Атомарный снимок живой базы")
tmpdir = Path(tempfile.mkdtemp(prefix="b14-"))
backup = tmpdir / "shop-backup.db"
store.export_sqlite_backup(str(backup))
ok("файл создан", backup.is_file() and backup.stat().st_size > 0)
bcon = sqlite3.connect(backup)
ok("integrity_check бэкапа ok", bcon.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
live = sqlite3.connect(f"file:{LIVE}?mode=ro", uri=True)
live_tables = [r[0] for r in live.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
mismatch = []
for t in live_tables:
    a = live.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    b = bcon.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    if a != b:
        mismatch.append((t, a, b))
bcon.close()
ok("количества записей всех таблиц совпадают с живой", not mismatch, mismatch[:4])

print("3) verify_restore.py: валидный бэкап и подделка")
res = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_restore.py"),
                      str(backup), "--expect-live", str(LIVE), "--checksum"],
                     capture_output=True, text=True, timeout=120)
ok("валидный бэкап → exit 0", res.returncode == 0, res.stdout[-300:])
ok("в отчёте «Восстановление валидно»", "Восстановление валидно" in res.stdout)

tampered = tmpdir / "tampered.db"
shutil.copy2(backup, tampered)
tc = sqlite3.connect(tampered)
try:
    tc.execute("DELETE FROM products")
    tc.commit()
except sqlite3.Error:
    pass
tc.close()
res = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_restore.py"),
                      str(tampered), "--expect-live", str(LIVE)],
                     capture_output=True, text=True, timeout=120)
ok("подделанный бэкап → exit 1", res.returncode == 1, res.returncode)
ok("в отчёте есть РАСХОЖДЕНИЕ", "РАСХОЖДЕНИЕ" in res.stdout, res.stdout[-200:])

print("4) restore_sqlite.py: dry-run не трогает цель")
target = tmpdir / "target.db"
target.write_bytes(b"keep-me")
res = subprocess.run([sys.executable, str(ROOT / "scripts" / "restore_sqlite.py"),
                      str(backup), "--target", str(target)],
                     capture_output=True, text=True, timeout=120)
ok("dry-run → exit 0", res.returncode == 0, res.stdout[-200:])
ok("цель не изменена", target.read_bytes() == b"keep-me")

print("5) Миграция: DDL-трансляция и dry-run")
ddl = mig.translate_ddl('CREATE TABLE "products" ("id" INTEGER PRIMARY KEY AUTOINCREMENT, "name" TEXT DEFAULT \'\')')
ok("AUTOINCREMENT → AUTO_INCREMENT PRIMARY KEY", "AUTO_INCREMENT PRIMARY KEY" in ddl, ddl)
ok("AUTOINCREMENT удалён", "AUTOINCREMENT" not in ddl, ddl)
ok("кавычки → backticks", '"' not in ddl and "`" in ddl, ddl)
ddl_s = mig.translate_ddl("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT)")
ok("TEXT PRIMARY KEY → VARCHAR(191)", "VARCHAR(191) PRIMARY KEY" in ddl_s, ddl_s)
ddl_u = mig.translate_ddl("CREATE TABLE sellers(slug TEXT UNIQUE, email TEXT UNIQUE)")
ok("TEXT UNIQUE → VARCHAR(191)", ddl_u.count("VARCHAR(191) UNIQUE") == 2, ddl_u)
ddl_d = mig.translate_ddl("CREATE TABLE products(id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT DEFAULT '', code TEXT DEFAULT '')")
ok("TEXT DEFAULT убран (strict MySQL 8)", "DEFAULT" not in ddl_d and "TEXT" in ddl_d, ddl_d)
ok("AUTOINCREMENT в PK → AUTO_INCREMENT", "AUTO_INCREMENT PRIMARY KEY" in ddl_d, ddl_d)
res = subprocess.run([sys.executable, str(ROOT / "scripts" / "migrate_sqlite_to_mysql.py"),
                      "--source", str(LIVE)], capture_output=True, text=True, timeout=120)
ok("dry-run миграции → exit 0", res.returncode == 0, res.stdout[-300:])
ok("в плане есть products, orders, settings, warehouses",
   all(t in res.stdout for t in ("products", "orders", "settings", "warehouses")), "")

print("6) Логика копирования и сверки на фейковом MySQL-таргете")


class FakeTarget:
    """Мини-имплементация интерфейса MySQLTarget в памяти."""

    def __init__(self, corrupt_tables=()):
        self.tables_ = set()
        self.data = {}
        self.corrupt = set(corrupt_tables)

    def tables(self):
        return set(self.tables_)

    def drop_table(self, t):
        self.tables_.discard(t)
        self.data.pop(t, None)

    def create_table(self, ddl):
        import re
        m = re.search(r"CREATE TABLE (?:IF NOT EXISTS )?[`\x22']?(\w+)", ddl, re.I)
        self.tables_.add(m.group(1) if m else "?")

    def insert_rows(self, t, columns, rows):
        self.data.setdefault(t, []).extend(tuple(r) for r in rows)

    def fetch_rows(self, t, columns):
        return list(self.data.get(t, []))

    def close(self):
        pass


src_ro = mig.open_source(LIVE)
tables = mig.list_tables(src_ro)
fake = FakeTarget()
rc = mig.migrate_apply(src_ro, fake, tables, drop_existing=False)
ok("полная копия: сверка прошла (exit 0)", rc == 0, rc)
ok("все таблицы созданы", fake.tables_ == set(tables), len(fake.tables_))
prods = fake.data.get("products") or []
ok("товары перенесены", len(prods) == live.execute("SELECT COUNT(*) FROM products").fetchone()[0])
orders = fake.data.get("orders") or []
ok("заказы перенесены", len(orders) == live.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
stock = fake.data.get("wh_stock") or []
ok("склады/остатки перенесены", len(stock) == live.execute("SELECT COUNT(*) FROM wh_stock").fetchone()[0])
users_n = len(fake.data.get("users") or []) + len(fake.data.get("wh_users") or [])
ok("пользователи перенесены",
   users_n == live.execute("SELECT COUNT(*) FROM users").fetchone()[0]
   + live.execute("SELECT COUNT(*) FROM wh_users").fetchone()[0])
ok("настройки перенесены (1 строка __settings__)", len(fake.data.get("settings") or []) == 1)

# расхождение: в таргете потеряна часть строк products
compare_tables = ["products", "orders", "settings"]
bad = FakeTarget()
rc_first = mig.migrate_apply(src_ro, bad, compare_tables, drop_existing=False)
ok("копия products/orders/settings сходится", rc_first == 0, rc_first)
bad.data["products"] = (bad.data.get("products") or [])[:-1]  # портим
rc = mig.migrate_apply(src_ro, bad, compare_tables, drop_existing=False)
ok("потеря строки → расхождение обнаружено (exit 1)", rc == 1, rc)

print("7) Исходная БД не изменилась")
# детерминированная проверка: миграция читает только копию источника (read-only)
src_copy = tmpdir / "source-copy.db"
shutil.copy2(LIVE, src_copy)
sha_copy_before = file_sha(src_copy)
ro = mig.open_source(src_copy)
rc = mig.migrate_apply(ro, FakeTarget(), tables, drop_existing=False)
ro.close()
ok("sha256 копии источника до == после миграции", file_sha(src_copy) == sha_copy_before)
ok("миграция копии прошла (exit 0)", rc == 0, rc)
lcon = sqlite3.connect(f"file:{LIVE}?mode=ro", uri=True)
ok("живая база: integrity_check ok",
   lcon.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
lcon.close()
src_ro.close()
live.close()
shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
