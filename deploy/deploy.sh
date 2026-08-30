#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BRANCH="arena/continue-marketplace-content"
DOMAIN="${DEPLOY_DOMAIN:-}"
EXPECTED_VERSION="${DEPLOY_EXPECTED_VERSION:-1.0.5}"
SKIP_PIP=0
SKIP_SMOKE=0
NO_CACHE=1
ALLOW_DIRTY=0

usage() {
  cat <<'EOF'
Usage:
  ./deploy/deploy.sh [--branch BRANCH] [--domain https://example.com] [--expected-version 1.0.5] [--skip-pip] [--skip-smoke] [--cache] [--allow-dirty]

Options:
  --branch BRANCH            Git branch to deploy (default: arena/continue-marketplace-content)
  --domain URL               Public base URL for post-deploy smoke-check
  --expected-version VER     Expected Android release version for smoke-check (default: 1.0.5)
  --skip-pip                 Skip `pip install -r telegram-shop/requirements.txt`
  --skip-smoke               Skip post-deploy smoke-check even if --domain is provided
  --cache                    Use cached docker build layers (default is --no-cache)
  --allow-dirty              Do not abort when repo has local uncommitted changes
  -h, --help                 Show this help
EOF
}

log() {
  printf '\n==> %s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --domain)
      DOMAIN="${2:-}"
      shift 2
      ;;
    --expected-version)
      EXPECTED_VERSION="${2:-}"
      shift 2
      ;;
    --skip-pip)
      SKIP_PIP=1
      shift
      ;;
    --skip-smoke)
      SKIP_SMOKE=1
      shift
      ;;
    --cache)
      NO_CACHE=0
      shift
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

cd "$REPO_ROOT"

if [ "$ALLOW_DIRTY" -ne 1 ] && [ -n "$(git status --porcelain)" ]; then
  git status --short >&2 || true
  die "Repository has uncommitted changes. Commit/stash them first or pass --allow-dirty."
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  die "Neither 'docker compose' nor 'docker-compose' is available."
fi

log "Repo root: $REPO_ROOT"
log "Updating branch: $BRANCH"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [ "$SKIP_PIP" -ne 1 ]; then
  log "Installing Python dependencies"
  python3 -m pip install -r telegram-shop/requirements.txt
fi

log "Restarting containers via: ${COMPOSE_CMD[*]}"
"${COMPOSE_CMD[@]}" down || true
if [ "$NO_CACHE" -eq 1 ]; then
  "${COMPOSE_CMD[@]}" build --no-cache
else
  "${COMPOSE_CMD[@]}" build
fi
"${COMPOSE_CMD[@]}" up -d

if [ -n "$DOMAIN" ] && [ "$SKIP_SMOKE" -ne 1 ]; then
  if [ -x "$REPO_ROOT/telegram-shop/scripts/post_deploy_smoke_check.sh" ]; then
    log "Running smoke-check for $DOMAIN (expected Android version: $EXPECTED_VERSION)"
    "$REPO_ROOT/telegram-shop/scripts/post_deploy_smoke_check.sh" "$DOMAIN" "$EXPECTED_VERSION"
  else
    die "Smoke-check script not found: telegram-shop/scripts/post_deploy_smoke_check.sh"
  fi
fi

log "Deploy finished"
printf 'Branch: %s\n' "$BRANCH"
if [ -n "$DOMAIN" ]; then
  printf 'Domain: %s\n' "$DOMAIN"
fi
printf 'Tip: verify APK 1.0.5 on a real Android device before merge into main.\n'
