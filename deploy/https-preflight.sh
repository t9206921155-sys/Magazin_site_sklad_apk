#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "usage: $0 https://host" >&2; exit 2; fi
url="$1"
[[ "$url" == https://* ]] || { echo 'HTTPS URL required' >&2; exit 1; }
command -v curl >/dev/null || { echo 'curl is required' >&2; exit 1; }
headers="$(curl -fsSIL --max-time 10 "$url")"
grep -qi '^HTTP/.* 2\|^HTTP/.* 3' <<<"$headers" || { echo 'endpoint did not return 2xx/3xx' >&2; exit 1; }
grep -qi '^strict-transport-security:' <<<"$headers" || echo 'warning: HSTS header is missing' >&2
printf 'HTTPS preflight OK: %s\n' "$url"
