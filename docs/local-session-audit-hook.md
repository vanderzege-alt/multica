# Local session audit hook

The hook is called from the shared `TaskService.CompleteTask` path after the task's terminal transaction commits. Codex, Hermes, and other runtime adapters therefore reach the same hook. It handles the failure mode where a provider callback is delivered more than once by keying artifacts to the stable task ID and completed timestamp; a repeated successful event reuses the verified report. A repeated failed event is recorded as another attempt and can recover on redelivery.

Skill binding applies to persistent `kind=user` agents created through `POST /agents`, including CLI copy operations, and the legacy onboarding assistant path. The ephemeral `kind=system` agent-builder carriers are excluded: they hold a short-lived configuration conversation and do not represent persistent workers. Copying with `--no-skills` still receives the mandatory audit skill from the server create path.

## Enable in a local build

Set these variables only for a local development server:

```sh
MULTICA_SESSION_AUDIT_ENABLED=true
MULTICA_SESSION_AUDIT_GENERATOR_ROOT=/path/to/agent-as-employee
MULTICA_SESSION_AUDIT_GENERATOR_SHA=46b39b0d6aca8ead90b5eac8be2fcb54d06067b1
MULTICA_SESSION_AUDIT_ARTIFACT_DIR=.multica/session-audit
```

The generator SHA defaults to the verified VAN-484 revision above. The hook checks the checkout HEAD before invoking `scripts/session_audit.py` with the verified `report` and `verify-report` CLI arguments. Reports failing preflight remain `REVIEW_REQUIRED`; the current session lifecycle matrix deliberately records no behavioral PASS. Missing tool inventory and isolation evidence remain unknown, so a healthy task completion is never misreported as an audit PASS. Runtime/model/effort and permission settings are read only.

## Storage and observability

For an issue task, artifacts are stored under:

```text
.multica/session-audit/<workspace-id>/<issue-id>/<task-id>/
```

Chat tasks use `no-issue` in place of the issue ID. `report.json` is the verified generator output; `report.md` is a manager-readable rendering of that JSON. `.lock` serializes redelivery. `hook-attempts.jsonl` records event identity, attempt number, timestamp, outcome and report digest. A failed invocation writes `latest-failure.json` and `failure.md` with a bounded recovery reason and never fabricates PASS.

Server logs emit `session audit hook completed` on success and `session audit hook failed` on invocation failure, keyed by task and issue IDs. The hook is post-commit and does not reverse completed work when report generation fails.

## Recovery

1. Check the server log for the task ID and inspect that task's artifact directory.
2. Confirm the configured generator checkout is at the pinned SHA and that Python can run its standard-library CLI.
3. Redeliver the same task completion callback; the task-ID key makes this safe. If callback redelivery is unavailable, rerun the issue to produce a new task and report, then retain the prior failed attempt for audit.
4. Confirm `report.json` verifies and the latest attempt is `report_verified`; keep `REVIEW_REQUIRED` when configuration evidence or matrix cases remain incomplete.

The local demonstration uses synthetic fixture data only; no production rollout is enabled by default.
