#!/usr/bin/env python3
"""Проверка восстановления SQLite-бэкапа (блок 14).

Что делает:
1. integrity_check бэкапа;
2. восстанавливает бэкап во ВРЕМЕННУЮ БД (в tempdir, рабочая база не трогается);
3. сверяет количества записей по всем таблицам с живой базой (--expect-live),
   опционально сверяет контрольные суммы строк;
4. отчёт + exit code (0 — восстановление валидно, 1 — нет).

Использование:
  python3 scripts/verify_restore.py backups/shop-20260908.db
  python3 scripts/verify_restore.py backup.db --expect-live data/shop.db --checksum
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

KEY_TABLES = ("products", "orders", "users", "warehouses", "wh_stock", "wh_users",
              "settings", "sellers", "reviews")


def open_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def tables(con: sqlite3.Connection) -> list:
    return [r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name").fetchall()]


def counts(con: sqlite3.Connection, tbs: list) -> dict:
    return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tbs}


def checksum(con: sqlite3.Connection, t: str) -> str:
    cols = [r["name"] for r in con.execute(f'PRAGMA table_info("{t}")').fetchall()]
    sel = ", ".join(f'"{c}"' for c in cols)
    lines = sorted("\x01".join("\x00" if v is None else ("b:" + v.hex() if isinstance(v, bytes) else str(v))
                              for v in row)
                   for row in con.execute(f'SELECT {sel} FROM "{t}"').fetchall())
    h = hashlib.sha256()
    for ln in lines:
        h.update(ln.encode("utf-8", "replace") + b"\n")
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify SQLite backup restore into a temp DB")
    ap.add_argument("backup", type=Path)
    ap.add_argument("--expect-live", type=Path, default=None,
                    help="живая база для сверки количеств записей")
    ap.add_argument("--checksum", action="store_true", help="сверить также контрольные суммы строк")
    ap.add_argument("--tables", default="", help="проверять только эти таблицы (через запятую)")
    args = ap.parse_args()

    if not args.backup.is_file():
        ap.error(f"бэкап не найден: {args.backup}")

    digest = hashlib.sha256(args.backup.read_bytes()).hexdigest()
    print(f"Бэкап: {args.backup} ({args.backup.stat().st_size} bytes)")
    print(f"SHA256: {digest}")

    con = sqlite3.connect(args.backup)
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    if integrity != "ok":
        print(f"ОШИБКА: integrity_check → {integrity}")
        return 1
    print("Integrity check: ok")

    # восстановление во временную БД: рабочая база не затрагивается
    with tempfile.TemporaryDirectory(prefix="restore-verify-") as td:
        tmp = Path(td) / "restored.db"
        shutil.copy2(args.backup, tmp)
        rst = open_ro(tmp)
        tbs = tables(rst)
        if args.tables:
            want = {x.strip() for x in args.tables.split(",") if x.strip()}
            tbs = [t for t in tbs if t in want]
        rc = counts(rst, tbs)
        missing = [t for t in KEY_TABLES if t not in tbs]
        if missing:
            print(f"ОШИБКА: в бэкапе нет ключевых таблиц: {', '.join(missing)}")
            return 1
        print(f"Восстановлено во временную БД: {len(tbs)} таблиц, записей: {sum(rc.values())}")

        problems = []
        if args.expect_live:
            if not args.expect_live.is_file():
                ap.error(f"живая база не найдена: {args.expect_live}")
            live = open_ro(args.expect_live)
            lc = counts(live, [t for t in tbs if t in tables(live)])
            live_tbs = set(tables(live))
            print("\nТаблица                     бэкап     живая   статус")
            for t in tbs:
                lcount = lc.get(t)
                if lcount is None:
                    status = "нет в живой"
                elif lcount != rc[t]:
                    status = "РАСХОЖДЕНИЕ"
                    problems.append(t)
                else:
                    status = "OK"
                    if args.checksum and checksum(rst, t) != checksum(live, t):
                        status = "СУММА РАСШОДИТСЯ"
                        problems.append(t)
                print(f"  {t:<24} {rc[t]:>9} {str(lcount):>9}   {status}")
            extra = [t for t in live_tbs if t not in tbs]
            if extra:
                print(f"  (таблиц нет в бэкапе: {', '.join(extra)})")
        else:
            print("Таблицы в бэкапе:", ", ".join(f"{t}={rc[t]}" for t in tbs[:12]),
                  "…" if len(tbs) > 12 else "")

        rst.close()

    if args.expect_live and problems:
        print(f"\nПРОВАЛ: расхождения в {len(problems)} таблицах: {', '.join(problems)}")
        return 1
    print("\nВосстановление валидно ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
