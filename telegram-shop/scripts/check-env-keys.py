#!/usr/bin/env python3
"""Check that .env.example documents every os.getenv key used by config.py."""
import re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
config=(root/'config.py').read_text()
env=(root/'.env.example').read_text() if (root/'.env.example').exists() else ''
keys=set(re.findall(r'os\.getenv\("([A-Z0-9_]+)"',config))
documented={line.split('=',1)[0].strip() for line in env.splitlines() if line and not line.lstrip().startswith('#') and '=' in line}
missing=sorted(keys-documented)
if missing:
 print('Missing .env.example keys:', ', '.join(missing)); raise SystemExit(1)
print(f'env keys: {len(keys)} documented, 0 missing')
