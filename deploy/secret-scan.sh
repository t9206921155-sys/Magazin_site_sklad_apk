#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Conservative scan: report likely credentials, never print matching content.
if git grep -n -I -E 'ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY' -- . ':!*.md' ':!staging.env.example' >/tmp/secret-scan.matches 2>/dev/null; then
  echo 'potential credential pattern found; inspect /tmp/secret-scan.matches' >&2
  exit 1
fi
echo 'secret scan OK'
