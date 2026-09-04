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

# Optional authenticated checks. Credentials are passed only via environment, never CLI/logs.
if [[ -n "${WH_LOGIN:-}" && -n "${WH_PASSWORD:-}" ]]; then
  token=$(curl -ksS --max-time 15 -H 'Content-Type: application/json' -d "{\"login\":\"$WH_LOGIN\",\"password\":\"$WH_PASSWORD\"}" "$BASE/api/warehouse/login" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token", ""))')
  if [[ -z "$token" ]]; then echo "FAIL warehouse login"; failed=1; else
    echo "OK   warehouse login"
    for path in /api/warehouse/warehouses /api/warehouse/printers /api/warehouse/reports/stock-value; do
      code=$(curl -ksS -o /dev/null -w '%{http_code}' --max-time 15 -H "X-Wh-Token: $token" -H "X-Admin-Token: $token" "$BASE$path")
      if [[ "$code" != "200" ]]; then echo "FAIL $path expected 200 got $code"; failed=1; else echo "OK   $path $code"; fi
    done
  fi
fi
