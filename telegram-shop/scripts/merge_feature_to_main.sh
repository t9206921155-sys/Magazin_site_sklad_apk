#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REMOTE="origin"
FEATURE_BRANCH="arena/continue-marketplace-content"
DO_PUSH=0
ALLOW_DIRTY=0

usage() {
  cat <<'EOF'
Usage:
  ./telegram-shop/scripts/merge_feature_to_main.sh [--remote origin] [--branch arena/continue-marketplace-content] [--push] [--allow-dirty]

Options:
  --remote NAME     Git remote to use (default: origin)
  --branch NAME     Feature branch to merge into main (default: arena/continue-marketplace-content)
  --push            Push main after successful merge
  --allow-dirty     Do not abort when repo has local uncommitted changes
  -h, --help        Show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '\n==> %s\n' "$*"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --remote)
      REMOTE="${2:-}"
      shift 2
      ;;
    --branch)
      FEATURE_BRANCH="${2:-}"
      shift 2
      ;;
    --push)
      DO_PUSH=1
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

log "Fetching remote branches"
git fetch "$REMOTE"

log "Updating main"
git checkout main
git pull --ff-only "$REMOTE" main

log "Merging ${REMOTE}/${FEATURE_BRANCH} into main"
git merge --no-ff "${REMOTE}/${FEATURE_BRANCH}" -m "Merge branch '${FEATURE_BRANCH}'"

if [ "$DO_PUSH" -eq 1 ]; then
  log "Pushing main to ${REMOTE}"
  git push "$REMOTE" main
fi

log "Merge complete"
printf 'main HEAD: %s\n' "$(git rev-parse HEAD)"
printf 'Merged branch: %s/%s\n' "$REMOTE" "$FEATURE_BRANCH"
if [ "$DO_PUSH" -eq 0 ]; then
  printf 'Push not executed. Run: git push %s main\n' "$REMOTE"
fi
