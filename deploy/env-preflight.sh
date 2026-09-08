#!/usr/bin/env bash
set -euo pipefail
# Validate configured adapter env without printing secret values.
vars=(CONTENT_CALLBACK_SECRET TELEGRAM_ADAPTER_TOKEN TELEGRAM_ADAPTER_ACCOUNT_ID VK_ADAPTER_TOKEN VK_ADAPTER_ACCOUNT_ID AVITO_ADAPTER_TOKEN AVITO_ADAPTER_ACCOUNT_ID META_ADAPTER_TOKEN META_ADAPTER_ACCOUNT_ID TIKTOK_ADAPTER_TOKEN TIKTOK_ADAPTER_ACCOUNT_ID WILDBERRIES_ADAPTER_TOKEN WILDBERRIES_ADAPTER_ACCOUNT_ID)
configured=0
for name in "${vars[@]}"; do
  value="${!name-}"
  if [[ -n "$value" ]]; then
    configured=$((configured+1))
    [[ "$value" != *$'\n'* ]] || { echo "$name contains newline" >&2; exit 1; }
    [[ "$value" != *"CHANGE_ME"* ]] || { echo "$name is placeholder" >&2; exit 1; }
  fi
done
printf 'env preflight OK: %s configured values\n' "$configured"
