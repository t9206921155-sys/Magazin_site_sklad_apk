#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "usage: $0 <backup-file>" >&2; exit 2; fi
backup="$1"
[[ -f "$backup" ]] || { echo "backup not found: $backup" >&2; exit 1; }
case "$backup" in *.sqlite|*.sqlite3|*.db|*.sql|*.gz|*.zst) ;; *) echo 'unsupported backup extension' >&2; exit 1;; esac
printf 'rollback preflight OK: %s\n' "$backup"
printf '%s\n' 'No restore was executed. Perform restore only on staging/production with an approved maintenance window.'
