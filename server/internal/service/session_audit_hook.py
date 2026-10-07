import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".audit-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def run(payload):
    agent = payload.get("manifest", {}).get("agent", {})
    if not isinstance(agent.get("display_name"), str) or not agent["display_name"].strip() or \
       not isinstance(agent.get("id"), str) or not agent["id"].strip():
        raise ValueError("agent identity is incomplete")
    root = Path(os.environ["MULTICA_SESSION_AUDIT_GENERATOR_ROOT"]).resolve()
    expected = os.environ.get("MULTICA_SESSION_AUDIT_GENERATOR_SHA", "46b39b0d6aca8ead90b5eac8be2fcb54d06067b1")
    actual = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True, timeout=5).stdout.strip()
    if actual != expected:
        raise ValueError("generator revision mismatch")

    task = payload["task"]
    key = task["id"]
    base = Path(os.environ.get("MULTICA_SESSION_AUDIT_ARTIFACT_DIR", ".multica/session-audit"))
    folder = base / payload["workspace_id"] / (payload.get("issue_id") or "no-issue") / key
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / ".lock", "a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        report_path = folder / "report.json"
        markdown_path = folder / "report.md"
        events_path = folder / "hook-attempts.jsonl"
        event_id = f"{key}:{task.get('completed_at') or 'completed'}"
        rebuilding = False
        if report_path.exists() and markdown_path.exists():
            prior_events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()] if events_path.exists() else []
            report_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
            markdown_hash = hashlib.sha256(markdown_path.read_bytes()).hexdigest()
            successful_event = next((row for row in reversed(prior_events)
                                     if row.get("event_id") == event_id and row.get("status") == "report_verified"), None)
            if successful_event:
                if successful_event.get("report_sha256") == report_hash and successful_event.get("markdown_sha256") == markdown_hash:
                    return {"status": "idempotent", "report": str(report_path)}
                rebuilding = True

        with tempfile.TemporaryDirectory(prefix="multica-session-audit-") as temp:
            temp = Path(temp)
            manifest = temp / "manifest.json"
            snapshot = temp / "snapshot.json"
            matrix = temp / "matrix.json"
            attempts = temp / "attempts.json"
            report = temp / "report.json"
            manifest.write_text(json.dumps(payload["manifest"], ensure_ascii=False), encoding="utf-8")
            snapshot.write_text(json.dumps(payload["snapshot"], ensure_ascii=False), encoding="utf-8")
            matrix.write_text(json.dumps(payload["matrix"], ensure_ascii=False), encoding="utf-8")
            attempts.write_text('{"schema_version":"1","attempts":[]}', encoding="utf-8")
            python = os.environ.get("MULTICA_SESSION_AUDIT_PYTHON", "python3")
            cli = root / "scripts/session_audit.py"
            command = [python, str(cli), "report", "--manifest", str(manifest), "--snapshot", str(snapshot),
                       "--matrix", str(matrix), "--attempts", str(attempts), "--output", str(report)]
            completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30, check=False)
            if completed.returncode not in (0, 3) or not report.is_file():
                raise ValueError("generator report failed")
            verified = subprocess.run([python, str(cli), "verify-report", "--manifest", str(manifest),
                                       "--snapshot", str(snapshot), "--matrix", str(matrix),
                                       "--report", str(report)], cwd=root, capture_output=True, text=True,
                                      timeout=30, check=False)
            if verified.returncode != 0:
                raise ValueError("generator report verification failed")
            report_data = json.loads(report.read_text(encoding="utf-8"))

        summary = report_data["summary"]
        markdown = "\n".join([
            "# Agent session audit",
            "",
            f"- Agent: {report_data['agent']['display_name']} (`{report_data['agent']['id']}`)",
            f"- Task: `{report_data['session_id']}`",
            f"- Runtime provider: {payload.get('runtime_provider') or 'UNKNOWN'}",
            f"- Audit status: **{summary['status']}**",
            f"- Matrix: {report_data['suite']['name']} v{report_data['suite']['version']} ({summary['reported_denominator']}/{summary['planned_denominator']} cases)",
            f"- Preflight: **{report_data['preflight']['status']}**",
            "",
            "## Results",
            "",
            "| Result | Count |",
            "|---|---:|",
            *[f"| {name} | {count} |" for name, count in sorted(summary["results"].items())],
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report_data["limitations"]],
            "",
        ])
        json_bytes = json.dumps(report_data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        atomic_write(report_path, json_bytes)
        atomic_write(markdown_path, markdown)
        for failure_path in (folder / "latest-failure.json", folder / "failure.md"):
            failure_path.unlink(missing_ok=True)
        rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()] if events_path.exists() else []
        report_hash = hashlib.sha256(json_bytes.encode()).hexdigest()
        markdown_hash = hashlib.sha256(markdown.encode()).hexdigest()
        if rebuilding or not any(row.get("event_id") == event_id and row.get("status") == "report_verified"
                   and row.get("report_sha256") == report_hash and row.get("markdown_sha256") == markdown_hash
                   for row in rows):
            rows.append({"event_id": event_id, "attempt": len(rows) + 1, "observed_at": datetime.now(timezone.utc).isoformat(),
                         "status": "report_verified", "report_sha256": report_hash,
                         "markdown_sha256": markdown_hash})
            atomic_write(events_path, "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        return {"status": summary["status"], "report": str(report_path)}


def main():
    payload = None
    try:
        payload = json.load(sys.stdin)
        result = run(payload)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        reason = "generator_or_input_failure"
        if isinstance(exc, ValueError):
            if "revision" in str(exc):
                reason = "generator_revision_mismatch"
            elif "identity" in str(exc):
                reason = "incomplete_agent_identity"
        if payload:
            try:
                task = payload["task"]
                workspace_id = payload["workspace_id"]
                task_id = task["id"]
                folder = (Path(os.environ.get("MULTICA_SESSION_AUDIT_ARTIFACT_DIR", ".multica/session-audit")) /
                          workspace_id / (payload.get("issue_id") or "no-issue") / task_id)
                event_id = f"{task_id}:{task.get('completed_at') or 'completed'}"
                folder.mkdir(parents=True, exist_ok=True)
                with open(folder / ".lock", "a", encoding="utf-8") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    failure = {"status": "REVIEW_REQUIRED", "reason": reason,
                               "recovery": "verify the local generator path and pinned revision, then retry task completion"}
                    atomic_write(folder / "latest-failure.json", json.dumps(failure, sort_keys=True, indent=2) + "\n")
                    atomic_write(folder / "failure.md", "# Session audit requires recovery\n\n"
                                 f"- Task: `{task_id}`\n- Status: **REVIEW_REQUIRED**\n- Reason: `{reason}`\n"
                                 "- Recovery: verify the local generator path and pinned revision, then retry task completion.\n")
                    events_path = folder / "hook-attempts.jsonl"
                    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()] if events_path.exists() else []
                    rows.append({"event_id": event_id, "attempt": len(rows) + 1,
                                 "observed_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "reason": reason})
                    atomic_write(events_path, "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
            except Exception:
                pass
        # Never echo input, paths, command output, or exception strings.
        print(json.dumps({"status": "REVIEW_REQUIRED", "reason": reason}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
