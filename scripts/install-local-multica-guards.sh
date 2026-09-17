#!/usr/bin/env bash
# Install git pre-push guard: refuse pushes when origin is multica-ai/multica.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$REPO_ROOT/.git/hooks/pre-push"

cat > "$HOOK" <<'EOF'
#!/bin/sh
# Auto-installed by scripts/install-local-multica-guards.sh — do not edit by hand.
set -eu
url=$(git remote get-url origin 2>/dev/null || true)
case "$url" in
  *multica-ai/multica*)
    echo "🚫 BLOCKED: origin is upstream multica-ai/multica ($url)"
    echo "   Local fork policy: push only to vanderzege-alt/multica"
    exit 1
    ;;
esac
exit 0
EOF
chmod +x "$HOOK"
echo "Installed pre-push guard: $HOOK"
