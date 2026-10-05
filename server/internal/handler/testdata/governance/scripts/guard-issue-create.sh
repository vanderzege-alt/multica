#!/usr/bin/env bash
# scripts/guard-issue-create.sh — Pre-creation mechanical guard for Multica issues.
#
# Anti-Stall & Anti-Orphan Gate:
#   1. Blocks active status (todo, in_progress, in_review) without an assignee (--assignee or --assignee-id).
#   2. Blocks issue creation without --description-file (or file missing ## Acceptance Criteria).
#   3. Blocks sub-issue creation under staged parent without --stage (or sub-issue missing --parent).
#   4. Blocks missing ## Definition of Done (P1a.2 Taxonomy Gate).
#   5. Blocks active status without taxonomy title prefix; epic slugs must be in registry (P1a.2).
#
# Usage:
#   scripts/guard-issue-create.sh [multica issue create flags...]
#
# Exit codes:
#   0 - validation passed
#   1 - validation failed (blocked)
#   2 - usage / invocation error

set -euo pipefail

usage() {
  cat <<EOF
Usage: $(basename "$0") [multica issue create arguments...]

Mechanical guard that validates issue creation parameters to prevent orphan/unassigned
tasks and malformed descriptions lacking Acceptance Criteria.

Enforced Rules:
  - Active status (todo, in_progress, in_review) MUST have --assignee or --assignee-id.
  - Must provide --description-file pointing to an existing file containing "## Acceptance Criteria" (or "## Acceptance criteria").
  - If --stage is provided, --parent must also be provided.
  - Sub-issues under staged parents must specify --stage.
  - Description must contain "## Definition of Done" (P1a.2).
  - Active status requires taxonomy title prefix; epic(<slug>) slug must exist in WORKSPACE_DOMAIN_REGISTRY.
EOF
}

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAXONOMY_GUARD="$REPO_ROOT/scripts/lint_issue_taxonomy.py"

status=""
assignee=""
assignee_id=""
description_file=""
description=""
description_stdin=false
parent=""
stage=""
title=""
metadata_args=()

args=("$@")
i=0
while [[ $i -lt ${#args[@]} ]]; do
  arg="${args[$i]}"
  case "$arg" in
    --status)
      status="${args[$((i+1))]:-}"
      i=$((i+2))
      ;;
    --assignee)
      assignee="${args[$((i+1))]:-}"
      i=$((i+2))
      ;;
    --assignee-id)
      assignee_id="${args[$((i+1))]:-}"
      i=$((i+2))
      ;;
    --description-file)
      description_file="${args[$((i+1))]:-}"
      i=$((i+2))
      ;;
    --description)
      description="${args[$((i+1))]:-}"
      i=$((i+2))
      ;;
    --description-stdin)
      description_stdin=true
      i=$((i+1))
      ;;
    --parent)
      parent="${args[$((i+1))]:-}"
      i=$((i+2))
      ;;
    --stage)
      stage="${args[$((i+1))]:-}"
      i=$((i+2))
      ;;
    --title)
      title="${args[$((i+1))]:-}"
      i=$((i+2))
      ;;
    --metadata)
      metadata_args+=("${args[$((i+1))]:-}")
      i=$((i+2))
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      i=$((i+1))
      ;;
  esac
done

status_lc="$(printf "%s" "$status" | tr "[:upper:]" "[:lower:]")"

# Rule 1: Validate active status requires assignee
ACTIVE_STATUSES=("todo" "in_progress" "in_review")
is_active_status="false"
for s in "${ACTIVE_STATUSES[@]}"; do
  if [[ "$status_lc" == "$s" ]]; then
    is_active_status="true"
    break
  fi
done

if [[ "$is_active_status" == "true" ]]; then
  if [[ -z "$assignee" && -z "$assignee_id" ]]; then
    echo "❌ BLOCKED [Anti-Orphan Gate]: Active status '$status' requires an explicit assignee (--assignee or --assignee-id)." >&2
    echo "To create an unassigned/parked task, set --status backlog." >&2
    exit 1
  fi
fi

# Rule 2: Description file & Acceptance Criteria check
if [[ -z "$description_file" ]]; then
  echo "❌ BLOCKED [Issue Standards Gate]: Issue creation must use --description-file <path> inside working directory (MUL-2904/MUL-4252)." >&2
  if [[ -n "$description" || "$description_stdin" == "true" ]]; then
    echo "Inline descriptions (--description / --description-stdin) are forbidden for agent-authored issues." >&2
  fi
  exit 1
fi

if [[ ! -f "$description_file" ]]; then
  echo "❌ BLOCKED [Issue Standards Gate]: Description file not found: $description_file" >&2
  exit 1
fi

# Validate presence of ## Acceptance Criteria in description_file
if ! grep -qiE "^##[[:space:]]+(Acceptance[[:space:]]+Criteria|Критерии[[:space:]]+при[её]мки)" "$description_file"; then
  echo "❌ BLOCKED [Scope & DoD Gate]: Description file '$description_file' is missing mandatory '## Acceptance Criteria' section." >&2
  exit 1
fi

# Rule 3: Stage and Parent hierarchy consistency
if [[ -n "$stage" && -z "$parent" ]]; then
  echo "❌ BLOCKED [Hierarchy Gate]: --stage requires --parent to be specified." >&2
  exit 1
fi

# If parent is specified and multica CLI is available, check if parent has stages
if [[ -n "$parent" && -z "$stage" ]] && command -v multica >/dev/null 2>&1; then
  children_json=$(multica issue children "$parent" --output json 2>/dev/null || true)
  if [[ -n "$children_json" && "$children_json" != "null" && "$children_json" != "[]" ]]; then
    has_stages=$(echo "$children_json" | grep -o ""stage":[[:space:]]*[1-9]" || true)
    if [[ -n "$has_stages" ]]; then
      echo "❌ BLOCKED [Hierarchy Gate]: Parent issue '$parent' has staged sub-issues. Child must specify --stage <N>." >&2
      exit 1
    fi
  fi
fi

# Rule 4: Taxonomy gate (P1a.2) — DoD, title prefix, registry slug, kind metadata
if [[ ! -f "$TAXONOMY_GUARD" ]]; then
  echo "❌ ERROR [Taxonomy Gate]: lint_issue_taxonomy.py not found at $TAXONOMY_GUARD" >&2
  exit 2
fi

taxonomy_cmd=(
  python3 "$TAXONOMY_GUARD" --guard
  --title "$title"
  --description-file "$description_file"
  --status "${status:-backlog}"
)
if (( ${#metadata_args[@]} > 0 )); then
  for meta in "${metadata_args[@]}"; do
    taxonomy_cmd+=(--metadata "$meta")
  done
fi

if ! "${taxonomy_cmd[@]}"; then
  exit 1
fi

echo "✅ PASS: Issue creation parameters validated successfully."
exit 0
