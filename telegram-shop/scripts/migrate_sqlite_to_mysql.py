#!/usr/bin/env python3
"""Миграция SQLite → MySQL/MariaDB с dry-run, сверкой и безопасным откатом (блок 14).

Безопасность по критериям приёмки блока:
- источник открывается в режиме read-only (`file:...?mode=ro`) — исходная БД
  повредить невозможно ни в dry-run, ни в --apply;
- по умолчанию dry-run: показывается план (таблицы и количества записей), ничего не пишется;
- --apply копирует данные и сверяет КАЖДУЮ таблицу: количество записей и SHA256
  канонической сериализации строк должны совпасть, иначе exit 1 с отчётом;
- откат: исходная SQLite остаётся рабочей базой (db_mode=vps), целевая MySQL
  независима; повторный запуск с --drop-existing начинает миграцию заново.

Использование:
  python3 scripts/migrate_sqlite_to_mysql.py                 # dry-run (только SQLite-сторона)
  python3 scripts/migrate_sqlite_to_mysql.py --host h --user u --password p --database shop --apply
  python3 scripts/migrate_sqlite_to_mysql.py --apply --drop-existing   # перезапись цели

Параметры MySQL можно брать из настроек склада (cloud.mysql_*) автоматически.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Таблицы, которые не нужно переносить (служебные для SQLite).
SKIP_TABLES = {"sqlite_sequence", "sqlite_stat1", "sqlite_stat4"}


def open_source(path: Path) -> sqlite3.Connection:
    """Read-only подключение к источнику: гарантирует целостность исходной БД."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def list_tables(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name").fetchall()
    return [r["name"] for r in rows if r["name"] not in SKIP_TABLES]


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def translate_ddl(sql: str) -> str:
    """SQLite CREATE → MySQL DDL (достаточно для схемы этого проекта).

    Строгий MySQL 8 не допускает: AUTOINCREMENT, PRIMARY KEY/UNIQUE на TEXT
    без длины, литеральный DEFAULT у TEXT. Поэтому:
    - INTEGER PRIMARY KEY (AUTOINCREMENT) → BIGINT (AUTO_INCREMENT) PRIMARY KEY;
    - TEXT PRIMARY KEY / TEXT UNIQUE → VARCHAR(191) … (191 — безопасный индекс
      для utf8mb4); ключи проекта (settings.k, promos.code, slug, login) короче;
    - TEXT DEFAULT '<lit>' → TEXT (умолчание убирается): приложение всегда
      вставляет все колонки явно, а миграция переносит полные строки.
    """
    out = sql.replace('"', "`")
    out = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
                 "BIGINT AUTO_INCREMENT PRIMARY KEY", out, flags=re.I)
    out = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\b", "BIGINT PRIMARY KEY", out, flags=re.I)
    out = re.sub(r"\bINTEGER\s+NOT\s+NULL\s+PRIMARY\s+KEY\b",
                 "BIGINT NOT NULL PRIMARY KEY", out, flags=re.I)
    out = re.sub(r"\bAUTOINCREMENT\b", "", out, flags=re.I)
    # TEXT с литеральным DEFAULT → просто TEXT (см. докстринг)
    out = re.sub(r"\bTEXT\s+DEFAULT\s+'(?:[^']|'')*'", "TEXT", out, flags=re.I)
    # TEXT ключи → VARCHAR(191)
    out = re.sub(r"\bTEXT\s+PRIMARY\s+KEY\b", "VARCHAR(191) PRIMARY KEY", out, flags=re.I)
    out = re.sub(r"\bTEXT\s+UNIQUE\b", "VARCHAR(191) UNIQUE", out, flags=re.I)
    return out


def _canon_value(v):
    if v is None:
        return "\x00"
    if isinstance(v, bytes):
        return "b:" + v.hex()
    return str(v)


def table_checksum(rows: list, columns: list[str]) -> str:
    """SHA256 по канонической сериализации множества строк (порядок не важен)."""
    idx = {c: i for i, c in enumerate(columns)}
    lines = []
    for r in rows:
        vals = [_canon_value(r[i]) for i in range(len(columns))]
        lines.append("\x01".join(vals))
    lines.sort()
    h = hashlib.sha256()
    for ln in lines:
        h.update(ln.encode("utf-8", "replace") + b"\n")
    return h.hexdigest()


class MySQLTarget:
    """Запись в MySQL/MariaDB через pymysql. Единственная точка записи."""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        import pymysql
        self._conn = pymysql.connect(host=host, port=int(port), user=user, password=password,
                                     database=database, charset="utf8mb4",
                                     autocommit=False)
        self.database = database

    def tables(self) -> set:
        with self._conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            return {r[0] for r in cur.fetchall()}

    def drop_table(self, table: str):
        with self._conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS `{table}`")

    def create_table(self, mysql_ddl: str):
        with self._conn.cursor() as cur:
            cur.execute(mysql_ddl)
        self._conn.commit()

    def insert_rows(self, table: str, columns: list[str], rows: list) -> int:
        if not rows:
            return 0
        cols = ", ".join(f"`{c}`" for c in columns)
        ph = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO `{table}` ({cols}) VALUES ({ph})"
        count = 0
        with self._conn.cursor() as cur:
            chunk = []
            for r in rows:
                chunk.append(tuple(r))
                if len(chunk) >= 200:
                    cur.executemany(sql, chunk)
                    count += len(chunk)
                    chunk = []
            if chunk:
                cur.executemany(sql, chunk)
                count += len(chunk)
        self._conn.commit()
        return count

    def fetch_rows(self, table: str, columns: list[str]) -> list:
        cols = ", ".join(f"`{c}`" for c in columns)
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT {cols} FROM `{table}`")
            return [tuple(r) for r in cur.fetchall()]

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def source_rows(con, table: str, columns: list[str]) -> list:
    cols = ", ".join(f'"{c}"' for c in columns)
    return [tuple(r) for r in con.execute(f"SELECT {cols} FROM \"{table}\"").fetchall()]


def mysql_credentials_from_settings() -> dict:
    """Настройки MySQL из конфигурации склада (cloud.mysql_*), если заданы."""
    try:
        from store import store  # noqa
        c = dict((store.settings.get("cloud") or {}))
        return {"host": c.get("mysql_host", ""), "port": int(c.get("mysql_port") or 3306),
                "user": c.get("mysql_user", ""), "password": c.get("mysql_password", ""),
                "database": c.get("mysql_database", "")}
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="SQLite → MySQL/MariaDB migration (dry-run by default)")
    ap.add_argument("--source", type=Path, default=Path("data/shop.db"))
    ap.add_argument("--host", default=""); ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default=""); ap.add_argument("--password", default="")
    ap.add_argument("--database", default="")
    ap.add_argument("--apply", action="store_true", help="реально писать в MySQL (по умолчанию dry-run)")
    ap.add_argument("--drop-existing", action="store_true", help="пересоздать таблицы на цели")
    args = ap.parse_args()

    if not args.source.is_file():
        ap.error(f"источник не найден: {args.source}")

    src = open_source(args.source)
    ok = src.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    if not ok:
        print("ОШИБКА: integrity_check источника не прошёл — миграция прервана.")
        return 1

    tables = list_tables(src)
    plan = []
    for t in tables:
        n = src.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        plan.append((t, n))

    print(f"Источник: {args.source} (read-only, integrity ok)")
    print(f"Таблиц к переносу: {len(tables)}, записей всего: {sum(n for _, n in plan)}")
    for t, n in plan:
        print(f"  {t:<24} {n:>8}")

    creds = {"host": args.host, "port": args.port, "user": args.user,
             "password": args.password, "database": args.database}
    if not all([creds["host"], creds["user"], creds["database"]]):
        auto = mysql_credentials_from_settings()
        for k, v in auto.items():
            creds[k] = creds[k] or v

    if not args.apply:
        print("\nDry-run: целевая MySQL не указана или не передан --apply — запись не выполнялась.")
        if not all([creds["host"], creds["user"], creds["database"]]):
            print("Для --apply задайте --host/--user/--database (или настройте cloud.mysql_* в админке).")
        print("Откат в любой момент: рабочая база остаётся SQLite (db_mode=vps).")
        return 0

    if not all([creds["host"], creds["user"], creds["database"]]):
        print("ОШИБКА: для --apply нужны --host/--user/--database (пароль можно --password).")
        return 1

    target = MySQLTarget(creds["host"], creds["port"], creds["user"], creds["password"],
                         creds["database"])
    try:
        return migrate_apply(src, target, tables, drop_existing=args.drop_existing)
    except Exception as e:
        print(f"\nОШИБКА миграции: {str(e)[:300]}")
        print("Исходная SQLite не повреждена (read-only). Целевую БД можно пересоздать: --drop-existing.")
        return 1
    finally:
        target.close()


def migrate_apply(src: sqlite3.Connection, target, tables: list[str],
                  drop_existing: bool = False) -> int:
    """Копирование таблиц и сверка количеств/контрольных сумм. Target инъецируется
    (MySQLTarget или фейк в тестах) — логика проверяется без реального MySQL."""
    report = []
    existing = target.tables()
    for t in tables:
        ddl_row = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        ddl = translate_ddl(ddl_row["sql"] or f"CREATE TABLE `{t}` (id BIGINT PRIMARY KEY)")
        if drop_existing and t in existing:
            target.drop_table(t)
            existing.discard(t)
        if t not in existing:
            target.create_table(ddl)
        columns = table_columns(src, t)
        rows = source_rows(src, t, columns)
        target.insert_rows(t, columns, rows)
    # ---------------- сверка ----------------
    mismatches = []
    for t in tables:
        columns = table_columns(src, t)
        srows = source_rows(src, t, columns)
        trows = target.fetch_rows(t, columns)
        s_count, t_count = len(srows), len(trows)
        s_sum = table_checksum(srows, columns)
        t_sum = table_checksum(trows, columns)
        match = s_count == t_count and s_sum == t_sum
        report.append((t, s_count, t_count, match))
        if not match:
            mismatches.append(t)
    print("\nСверка источник → MySQL:")
    for t, sc, tc, m in report:
        mark = "OK " if m else "РАСХОЖДЕНИЕ"
        print(f"  [{mark}] {t:<24} {sc:>8} → {tc:>8}")
    if mismatches:
        print(f"\nОШИБКА: расхождение в {len(mismatches)} таблицах: {', '.join(mismatches)}")
        print("Откат: целевая MySQL не является рабочей базой; перезапустите с --drop-existing.")
        return 1
    print("\nМиграция завершена: количества и контрольные суммы совпадают по всем таблицам.")
    print("Исходная SQLite не изменялась (read-only). Переключение: db_mode=mysql в настройках склада.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
