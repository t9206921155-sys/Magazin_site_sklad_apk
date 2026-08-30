#!/usr/bin/env python3
"""Создаёт снимок локальной SQLite-базы и отправляет его в S3-совместимое хранилище.

По умолчанию берёт настройки из Store.settings['cloud']:
- provider=s3
- endpoint / access key / secret key
- backup_bucket (например shop-backups)
- backup_prefix (например sqlite)

Пример:
  cd /opt/Magazin_site_sklad_apk
  python3 telegram-shop/scripts/backup_sqlite_to_s3.py

Переопределение bucket/prefix вручную:
  python3 telegram-shop/scripts/backup_sqlite_to_s3.py --bucket shop-backups --prefix sqlite/manual
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite backup -> S3-compatible object storage")
    parser.add_argument("--bucket", default="", help="Override backup bucket")
    parser.add_argument("--prefix", default="", help="Override backup prefix/folder")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import cloudstore  # noqa: E402
    from store import store  # noqa: E402

    res = cloudstore.backup_db_to_cloud(
        store,
        bucket=args.bucket or None,
        prefix=args.prefix or None,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
