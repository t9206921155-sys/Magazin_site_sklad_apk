#!/usr/bin/env python3
"""Delete old S3 backups. Dry-run by default; pass --apply to delete."""
import argparse,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--keep',type=int,default=30);p.add_argument('--apply',action='store_true');a=p.parse_args();root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from store import store
import cloudstore
c=store.settings.get('cloud') or {}; client=cloudstore.backup_storage_from_cloud(c); r=client.list_backups(c.get('backup_prefix','sqlite')+'/')
if not r.get('ok'): raise SystemExit(r.get('error','list failed'))
keys=sorted(r['keys'],reverse=True); old=keys[a.keep:]
print(f'found={len(keys)} keep={a.keep} delete={len(old)} dry_run={not a.apply}')
if a.apply:
 for k in old: print(client.delete_backup(k))
