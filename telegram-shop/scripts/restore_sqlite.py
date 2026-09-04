#!/usr/bin/env python3
"""Safe local SQLite restore helper. Default is dry-run; use --apply explicitly."""
import argparse, shutil, sqlite3, hashlib
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument('backup', type=Path); p.add_argument('--target', type=Path, default=Path('data/shop.db')); p.add_argument('--apply', action='store_true'); p.add_argument('--backup-current', action='store_true'); a=p.parse_args()
    if not a.backup.is_file(): p.error('backup file not found')
    con=sqlite3.connect(a.backup); ok=con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; con.close()
    if not ok: p.error('SQLite integrity check failed')
    digest=hashlib.sha256(a.backup.read_bytes()).hexdigest()
    print(f'Backup OK: {a.backup} ({a.backup.stat().st_size} bytes)')
    print(f'SHA256: {digest}')
    print(f'Target: {a.target}')
    if not a.apply: print('Dry-run only. Add --apply to replace target.'); return 0
    if a.target.resolve()==a.backup.resolve(): p.error('target must differ from backup')
    a.target.parent.mkdir(parents=True, exist_ok=True)
    if a.target.exists() and a.backup_current:
        current=a.target.with_suffix(a.target.suffix+'.before-restore'); shutil.copy2(a.target,current); print(f'Current database backed up to {current}')
    tmp=a.target.with_suffix(a.target.suffix+'.restore-tmp'); shutil.copy2(a.backup,tmp); tmp.replace(a.target); print('Restored successfully'); return 0
if __name__=='__main__': raise SystemExit(main())
