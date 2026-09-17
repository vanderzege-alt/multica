#!/usr/bin/env bash
# Land an upstream multica-ai/multica PR into the local fork only (vanderzege-alt/multica).
#
# Usage: bash scripts/land-upstream-multica-pr.sh <upstream_pr_number> [--dry-run]
#
# NEVER opens or merges a PR on multica-ai/multica — fetch + merge into local main only.
set -euo pipefail

UPSTREAM_REPO="multica-ai/multica"
LOCAL_REPO="vanderzege-alt/multica"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PR_NUM="${1:-}"
DRY_RUN=0
if [ "${2:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

if [ -z "$PR_NUM" ]; then
  echo "Usage: bash scripts/land-upstream-multica-pr.sh <upstream_pr_number> [--dry-run]" >&2
  exit 2
fi

python3 "$SCRIPT_DIR/guard_local_multica_only.py" "land-upstream-multica-pr.sh $PR_NUM" >/dev/null

META=$(gh pr view "$PR_NUM" --repo "$UPSTREAM_REPO" --json state,mergeable,headRefName,headRepositoryOwner,title 2>/dev/null) || {
  echo "🚫 Failed to read upstream PR #$PR_NUM from $UPSTREAM_REPO" >&2
  exit 1
}

STATE=$(echo "$META" | python3 -c "import json,sys; print(json.load(sys.stdin).get('state',''))")
if [ "$STATE" = "MERGED" ]; then
  echo "ℹ️  Upstream PR #$PR_NUM already merged upstream; landing head commit into local fork anyway."
fi

HEAD_BRANCH=$(echo "$META" | python3 -c "import json,sys; print(json.load(sys.stdin)['headRefName'])")
HEAD_OWNER=$(echo "$META" | python3 -c "import json,sys; print(json.load(sys.stdin)['headRepositoryOwner']['login'])")
TITLE=$(echo "$META" | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))")

echo "📥 Landing upstream PR #$PR_NUM ($TITLE)"
echo "   head: ${HEAD_OWNER}:${HEAD_BRANCH}"
echo "   target: $LOCAL_REPO main (local fork only)"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY_RUN: would merge ${HEAD_OWNER}:${HEAD_BRANCH} into $LOCAL_REPO main"
  exit 0
fi

cd "$REPO_ROOT"
ORIGIN_URL=$(git remote get-url origin 2>/dev/null || true)
if echo "$ORIGIN_URL" | grep -q 'multica-ai/multica'; then
  echo "🚫 BLOCKED: git origin points at upstream $UPSTREAM_REPO ($ORIGIN_URL)" >&2
  echo "   Set origin to https://github.com/$LOCAL_REPO.git" >&2
  exit 1
fi

git fetch origin main
git checkout main
git pull --ff-only origin main

git fetch "https://github.com/${HEAD_OWNER}/multica.git" "$HEAD_BRANCH"
git merge --no-ff "FETCH_HEAD" -m "$(cat <<EOF
Land upstream multica PR #$PR_NUM into local fork

Upstream: $UPSTREAM_REPO#$PR_NUM (${HEAD_OWNER}:${HEAD_BRANCH})
Policy: local fork only — no publish to multica-ai/multica.
EOF
)"

if [ -f tools/test_multica_orchestrator_watcher.py ]; then
  python3 -m unittest tools/test_multica_orchestrator_watcher.py -q
fi

git push origin main
echo "✅ Landed upstream PR #$PR_NUM into $LOCAL_REPO @ $(git rev-parse --short HEAD)"
