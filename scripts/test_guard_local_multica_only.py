#!/usr/bin/env python3
"""Self-check for guard_local_multica_only.py."""
from __future__ import annotations

import unittest

from guard_local_multica_only import check_command


class GuardTests(unittest.TestCase):
    def test_blocks_upstream_merge(self) -> None:
        allowed, _ = check_command("gh pr merge 801 --repo multica-ai/multica --merge")
        self.assertFalse(allowed)

    def test_blocks_upstream_create(self) -> None:
        allowed, _ = check_command(
            "gh pr create --repo multica-ai/multica --head vanderzege-alt:fix/foo --base main"
        )
        self.assertFalse(allowed)

    def test_allows_upstream_view(self) -> None:
        allowed, _ = check_command("gh pr view 801 --repo multica-ai/multica --json title")
        self.assertTrue(allowed)

    def test_allows_upstream_diff(self) -> None:
        allowed, _ = check_command("gh pr diff 801 --repo multica-ai/multica")
        self.assertTrue(allowed)

    def test_blocks_upstream_git_push(self) -> None:
        allowed, _ = check_command("git push https://github.com/multica-ai/multica.git main")
        self.assertFalse(allowed)

    def test_allows_local_fork_merge(self) -> None:
        allowed, _ = check_command("gh pr merge 42 --repo vanderzege-alt/multica --merge")
        self.assertTrue(allowed)

    def test_allows_unrelated_gh_merge(self) -> None:
        allowed, _ = check_command("gh pr merge 460 --squash")
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
