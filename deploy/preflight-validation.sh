#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
printf '%s\n' '[preflight] syntax checks'
"$ROOT/deploy/env-preflight.sh"
printf '%s\n' '[preflight] secret scan'
"$ROOT/deploy/secret-scan.sh"
python3 -m py_compile telegram-shop/api.py telegram-shop/store.py marketing_adapters.py
printf '%s\n' '[preflight] test suite'
python3 -m pytest -q tests
printf '%s\n' '[preflight] executable mode check'
if git diff --summary | grep -qi 'mode change'; then
  echo 'mode changes detected; aborting' >&2
  exit 1
fi
printf '%s\n' '[preflight] schema declarations'
python3 - <<'PY2'
from pathlib import Path
schema=Path('telegram-shop/store.py').read_text()
for table in ('content_jobs','campaigns','campaign_publications'):
    assert f'CREATE TABLE IF NOT EXISTS {table}' in schema, table
print('content/campaign schema declarations present')
PY2
printf '%s\n' '[preflight] production publish remains adapter-gated'
python3 - <<'PY'
from marketing_adapters import ADAPTERS
assert ADAPTERS and all(cls().diagnostics()['dry_run'] for cls in ADAPTERS.values())
print(f'{len(ADAPTERS)} adapters are dry-run gated')
PY
printf '%s\n' '[preflight] OK'
