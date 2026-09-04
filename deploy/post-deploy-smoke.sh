#!/usr/bin/env bash
set -uo pipefail
BASE="${1:?Usage: $0 https://example.com}"
BASE="${BASE%/}"; failed=0
check(){ code=$(curl -LksS -o /dev/null -w '%{http_code}' --max-time 15 "$BASE$1"); if [[ "$code" != "$2" ]]; then echo "FAIL $1 expected $2 got $code"; failed=1; else echo "OK   $1 $code"; fi; }
check /health/live 200
check /health/ready 200
check /api/health 200
check / 200
check /catalog 200
check /app 200
check /warehouse/ 200
check /sitemap.xml 200
exit "$failed"
