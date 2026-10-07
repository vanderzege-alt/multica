import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import session_audit_hook as hook


class SessionAuditHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifacts = self.root / "artifacts"
        self.env = mock.patch.dict(os.environ, {
            "MULTICA_SESSION_AUDIT_GENERATOR_ROOT": str(self.root / "generator"),
            "MULTICA_SESSION_AUDIT_GENERATOR_SHA": "verified-sha",
            "MULTICA_SESSION_AUDIT_ARTIFACT_DIR": str(self.artifacts),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.payload = {
            "workspace_id": "workspace-test",
            "issue_id": "issue-test",
            "task": {"id": "task-test", "completed_at": "2026-10-06T10:00:00Z"},
            "manifest": {"agent": {"display_name": "Synthetic Worker", "id": "synthetic-id"}},
            "snapshot": {}, "matrix": {},
        }

    def test_generator_revision_mismatch_persists_review_required_and_retry_provenance(self):
        def wrong_head(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 0, stdout="wrong-sha\n", stderr="")

        with mock.patch.object(hook.subprocess, "run", side_effect=wrong_head):
            for _ in range(2):
                with mock.patch.object(hook.sys, "stdin", io.StringIO(json.dumps(self.payload))), \
                     contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(hook.main(), 1)

        folder = self.artifacts / "workspace-test" / "issue-test" / "task-test"
        failure = json.loads((folder / "latest-failure.json").read_text(encoding="utf-8"))
        attempts = [json.loads(line) for line in (folder / "hook-attempts.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(failure["status"], "REVIEW_REQUIRED")
        self.assertEqual(failure["reason"], "generator_revision_mismatch")
        self.assertEqual([row["attempt"] for row in attempts], [1, 2])
        self.assertTrue((folder / "failure.md").is_file())

    def test_missing_agent_identity_is_fail_closed_and_does_not_call_generator(self):
        self.payload["manifest"] = {"agent": {"display_name": "", "id": "synthetic-id"}}
        with mock.patch.object(hook.subprocess, "run") as run, \
             mock.patch.object(hook.sys, "stdin", io.StringIO(json.dumps(self.payload))), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(hook.main(), 1)
        run.assert_not_called()
        folder = self.artifacts / "workspace-test" / "issue-test" / "task-test"
        failure = json.loads((folder / "latest-failure.json").read_text(encoding="utf-8"))
        self.assertEqual(failure["status"], "REVIEW_REQUIRED")
        self.assertEqual(failure["reason"], "incomplete_agent_identity")

    def test_verified_report_is_idempotent_for_duplicate_completion_event(self):
        report_data = {
            "agent": {"display_name": "Synthetic Worker", "id": "synthetic-id"},
            "session_id": "task-test", "suite": {"name": "synthetic", "version": "1"},
            "summary": {"status": "REVIEW_REQUIRED", "reported_denominator": 1,
                        "planned_denominator": 1, "results": {"PASS": 0}},
            "preflight": {"status": "BLOCKED"}, "limitations": ["synthetic incomplete inventory"],
        }
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[0] == "git":
                return subprocess.CompletedProcess(command, 0, stdout="verified-sha\n", stderr="")
            if "report" in command:
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps(report_data), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            first = hook.run(self.payload)
            second = hook.run(self.payload)
            self.assertEqual(first["status"], "REVIEW_REQUIRED")
            self.assertEqual(second["status"], "idempotent")
            self.assertEqual(len(calls), 4)  # duplicate checks the pinned SHA but skips generation
            report_commands = [call for call in calls if "report" in call]
            self.assertEqual(len(report_commands), 1)
            self.assertIn("--manifest", report_commands[0])
            self.assertIn("--snapshot", report_commands[0])
            self.assertIn("--matrix", report_commands[0])
            self.assertIn("--attempts", report_commands[0])
            self.assertTrue((Path(first["report"]).with_suffix(".md")).is_file())
            Path(first["report"]).write_text("tampered", encoding="utf-8")
            repaired = hook.run(self.payload)
        self.assertEqual(repaired["status"], "REVIEW_REQUIRED")
        self.assertEqual(len([call for call in calls if "report" in call]), 2)
        attempts = [json.loads(line) for line in (Path(first["report"]).parent / "hook-attempts.jsonl").read_text().splitlines()]
        self.assertEqual([row["attempt"] for row in attempts], [1, 2])


if __name__ == "__main__":
    unittest.main()
