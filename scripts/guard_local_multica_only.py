#!/usr/bin/env python3
"""Block mutating GitHub/git operations against upstream multica-ai/multica.

Upstream Multica PRs (#759+, #801, …) land only in the local fork
(vanderzege-alt/multica). Read-only gh queries against upstream are allowed.

Exit codes: 0 allowed, 1 blocked, 2 usage/config error.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

UPSTREAM_REPO = "multica-ai/multica"
LOCAL_FORK_REPO = "vanderzege-alt/multica"
SKIP_ENV = "SKIP_AGENT_SAFETY_GUARDS"

READ_ONLY_GH = re.compile(
    r"\bgh\s+pr\s+(view|diff|checks|list|comment\s+list)\b",
    re.IGNORECASE,
)
MUTATING_GH = re.compile(
    r"\bgh\s+pr\s+(create|merge|close|reopen|edit|ready|review|update-branch|delete)\b",
    re.IGNORECASE,
)
MUTATING_GH_API = re.compile(
    r"\bgh\s+api\s+.*repos/multica-ai/multica.*\b(merge|pulls/.*/merge)\b",
    re.IGNORECASE,
)
UPSTREAM_GIT_PUSH = re.compile(
    r"\bgit\s+push\b.*(?:multica-ai/multica|git@github\.com:multica-ai/multica)",
    re.IGNORECASE,
)
UPSTREAM_REMOTE_SET = re.compile(
    r"\bgit\s+remote\s+set-url\b.*multica-ai/multica",
    re.IGNORECASE,
)


def _mentions_upstream(command: str) -> bool:
    lowered = command.lower()
    return UPSTREAM_REPO in lowered or "multica-ai/multica" in lowered


def check_command(command: str) -> tuple[bool, str]:
    """Return (allowed, message)."""
    if not _mentions_upstream(command):
        return True, "No upstream multica target"

    if READ_ONLY_GH.search(command):
        return True, "Read-only gh pr command against upstream allowed"

    if MUTATING_GH.search(command) and _mentions_upstream(command):
        return (
            False,
            f"Mutating gh pr against upstream {UPSTREAM_REPO} is forbidden; "
            f"land via scripts/land-upstream-multica-pr.sh into {LOCAL_FORK_REPO}",
        )

    if MUTATING_GH_API.search(command):
        return False, f"Mutating gh api against upstream {UPSTREAM_REPO} is forbidden"

    if UPSTREAM_GIT_PUSH.search(command) or UPSTREAM_REMOTE_SET.search(command):
        return False, f"git push/remote to upstream {UPSTREAM_REPO} is forbidden"

    return True, "Upstream mention without blocked mutating pattern"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", help="Shell command to evaluate")
    parser.add_argument("--stdin", action="store_true", help="Read command from stdin")
    args = parser.parse_args(argv)

    if os.environ.get(SKIP_ENV) == "1":
        print(f"⚠️ {SKIP_ENV}=1 — guard disabled")
        return 0

    command = args.command or ""
    if args.stdin:
        command = sys.stdin.read().strip()
    if not command:
        parser.error("command required")

    allowed, message = check_command(command)
    if allowed:
        print(message)
        return 0
    print(f"🚫 BLOCKED: {message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
