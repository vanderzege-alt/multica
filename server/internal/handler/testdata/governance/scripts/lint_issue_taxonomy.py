#!/usr/bin/env python3
"""Read-only issue taxonomy linter — WARN-only audit (P1a.1).

Audits Multica issues for title prefix compliance, epic registry slugs, and
mandatory AC/DoD sections. Mirrors Hermes ``backlog_lint.py`` contract:
  - exit 0 on findings (WARN lines only)
  - silent stdout when zero findings
  - exit 1 when registry file missing (misconfiguration)
  - exit 2 when multica CLI missing or issue fetch fails
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / "docs" / "WORKSPACE_DOMAIN_REGISTRY.md"

TITLE_PREFIX_RE = re.compile(
    r"^(epic|feat|impl|gov|ops|research)\(([^)]+)\):\s+.+",
    re.IGNORECASE,
)
EPIC_SLUG_RE = re.compile(r"^epic\(([^)]+)\):\s+.+", re.IGNORECASE)
AC_PATTERN = re.compile(
    r"^##\s+(Acceptance\s+Criteria|Критерии\s+при[её]мки)",
    re.IGNORECASE | re.MULTILINE,
)
DOD_PATTERN = re.compile(
    r"^##\s+(Definition\s+of\s+Done|DoD\b|Критерии\s+завершения)",
    re.IGNORECASE | re.MULTILINE,
)

VALID_KINDS = frozenset({"product", "platform", "service", "platform-cross"})
VALID_STATUSES = frozenset({"active", "paused", "proposed"})
ACTIVE_ISSUE_STATUSES = frozenset({"todo", "in_progress", "in_review"})
TITLE_PREFIX_TYPES = frozenset({"epic", "feat", "impl", "gov", "ops", "research"})


@dataclass(frozen=True)
class RegistryEntry:
    slug: str
    kind: str
    status: str


@dataclass(frozen=True)
class Finding:
    kind: str
    message: str
    issue_id: str = ""
    identifier: str = ""


@dataclass(frozen=True)
class CreateViolation:
    gate: str
    message: str


def _is_separator_row(cells: list[str]) -> bool:
    return all(
        c.replace(":", "").replace("-", "").strip() == "" and c.replace(":", "").strip()
        for c in cells
    )


def parse_registry(registry_path: Path) -> dict[str, RegistryEntry]:
    """Parse slug rows from WORKSPACE_DOMAIN_REGISTRY.md table."""
    text = registry_path.read_text(encoding="utf-8")
    entries: dict[str, RegistryEntry] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")][1:-1]
        if not cells or cells[0].lower() == "slug":
            continue
        if _is_separator_row(cells):
            continue
        if len(cells) < 3:
            continue
        slug = cells[0].strip()
        if not slug or slug.startswith("**"):
            continue
        kind = cells[1].strip().lower()
        status = cells[2].strip().lower()
        if kind not in VALID_KINDS or status not in VALID_STATUSES:
            continue
        entries[slug] = RegistryEntry(slug=slug, kind=kind, status=status)
    if not entries:
        raise ValueError(f"No registry slugs parsed from {registry_path}")
    return entries


def _issue_label(issue: dict) -> str:
    ident = issue.get("identifier") or ""
    number = issue.get("number")
    if ident:
        return ident
    if number is not None:
        return f"#{number}"
    return issue.get("id") or "unknown"


def validate_create(
    title: str,
    description: str,
    status: str,
    registry: dict[str, RegistryEntry],
    metadata: dict[str, str] | None = None,
) -> list[CreateViolation]:
    """Blocking validation for guard-issue-create (P1a.2).

    Rules:
      - DoD section required (all statuses).
      - Active statuses require taxonomy title prefix.
      - epic(<slug>) requires slug in registry; active status requires active slug.
      - paused/proposed slugs blocked for active statuses.
      - Optional metadata domain_kind must match registry kind for epics.
    """
    violations: list[CreateViolation] = []
    status_lc = (status or "backlog").strip().lower()
    is_active = status_lc in ACTIVE_ISSUE_STATUSES
    metadata = metadata or {}
    title = (title or "").strip()
    description = description or ""

    if not DOD_PATTERN.search(description):
        violations.append(
            CreateViolation(
                gate="Scope & DoD Gate",
                message=(
                    "Description is missing mandatory '## Definition of Done' section "
                    "(or '## DoD' / '## Критерии завершения')."
                ),
            )
        )

    prefix_match = TITLE_PREFIX_RE.match(title) if title else None

    if is_active and title and not prefix_match:
        violations.append(
            CreateViolation(
                gate="Taxonomy Gate",
                message=(
                    f"Active status '{status}' requires taxonomy title prefix "
                    f"(epic|feat|impl|gov|ops|research(<scope>): …): '{title}'"
                ),
            )
        )

    if prefix_match:
        prefix_type = prefix_match.group(1).lower()
        scope = prefix_match.group(2).strip()
        if prefix_type not in TITLE_PREFIX_TYPES:
            violations.append(
                CreateViolation(
                    gate="Taxonomy Gate",
                    message=f"Unknown taxonomy prefix '{prefix_type}' in title.",
                )
            )
        if prefix_type == "epic":
            entry = registry.get(scope)
            if not entry:
                violations.append(
                    CreateViolation(
                        gate="Registry Gate",
                        message=(
                            f"epic slug '{scope}' not in WORKSPACE_DOMAIN_REGISTRY "
                            f"(register via gov(registry): register domain {scope})."
                        ),
                    )
                )
            else:
                if is_active and entry.status != "active":
                    violations.append(
                        CreateViolation(
                            gate="Registry Gate",
                            message=(
                                f"epic slug '{scope}' has registry status '{entry.status}'; "
                                f"active issue status requires an active registry slug "
                                f"(use --status backlog for paused/proposed domains)."
                            ),
                        )
                    )
                declared_kind = metadata.get("domain_kind")
                if declared_kind and declared_kind != entry.kind:
                    violations.append(
                        CreateViolation(
                            gate="Kind Metadata Gate",
                            message=(
                                f"metadata domain_kind='{declared_kind}' does not match "
                                f"registry kind '{entry.kind}' for slug '{scope}'."
                            ),
                        )
                    )

    return violations


def lint_issue(issue: dict, registry: dict[str, RegistryEntry]) -> list[Finding]:
    findings: list[Finding] = []
    label = _issue_label(issue)
    issue_id = str(issue.get("id") or "")
    title = (issue.get("title") or "").strip()
    description = issue.get("description") or ""

    prefix_match = TITLE_PREFIX_RE.match(title)
    prefix_type: str | None = None
    if not prefix_match:
        findings.append(
            Finding(
                kind="title_prefix",
                message=f"{label}: title missing taxonomy prefix "
                f"(expected epic|feat|impl|gov|ops|research(<scope>): …): '{title}'",
                issue_id=issue_id,
                identifier=label,
            )
        )
    else:
        prefix_type = prefix_match.group(1).lower()
        scope = prefix_match.group(2).strip()
        if prefix_type == "epic":
            if scope not in registry:
                findings.append(
                    Finding(
                        kind="epic_slug_unknown",
                        message=f"{label}: epic slug '{scope}' not in WORKSPACE_DOMAIN_REGISTRY",
                        issue_id=issue_id,
                        identifier=label,
                    )
                )
        elif not issue.get("parent_issue_id"):
            findings.append(
                Finding(
                    kind="missing_parent",
                    message=(
                        f"{label}: {prefix_type} issues require parent epic link "
                        f"(parent_issue_id unset)"
                    ),
                    issue_id=issue_id,
                    identifier=label,
                )
            )

    if not AC_PATTERN.search(description):
        findings.append(
            Finding(
                kind="missing_ac",
                message=f"{label}: description missing '## Acceptance Criteria' section",
                issue_id=issue_id,
                identifier=label,
            )
        )

    if not DOD_PATTERN.search(description):
        findings.append(
            Finding(
                kind="missing_dod",
                message=f"{label}: description missing '## Definition of Done' section",
                issue_id=issue_id,
                identifier=label,
            )
        )

    return findings


def lint_issues(issues: list[dict], registry: dict[str, RegistryEntry]) -> list[Finding]:
    findings: list[Finding] = []
    for issue in issues:
        findings.extend(lint_issue(issue, registry))
    return findings


def load_issues_from_json(raw: str) -> list[dict]:
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "issues" in data:
        return list(data["issues"])
    raise ValueError("JSON must be an issues array or {\"issues\": [...]} object")


def fetch_issues_via_cli(limit: int = 100) -> list[dict]:
    if not shutil_which("multica"):
        raise RuntimeError("multica CLI not found in PATH")
    issues: list[dict] = []
    offset = 0
    while True:
        result = subprocess.run(
            [
                "multica",
                "issue",
                "list",
                "--output",
                "json",
                "--limit",
                str(limit),
                "--offset",
                str(offset),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"multica issue list failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        payload = json.loads(result.stdout)
        batch = payload.get("issues") or []
        issues.extend(batch)
        if not payload.get("has_more"):
            break
        offset += len(batch)
        if not batch:
            break
    return issues


def shutil_which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd)


def run_lint(
    issues: list[dict],
    registry_path: Path,
) -> tuple[list[Finding], dict[str, RegistryEntry]]:
    if not registry_path.is_file():
        raise FileNotFoundError(f"Registry file not found: {registry_path}")
    registry = parse_registry(registry_path)
    return lint_issues(issues, registry), registry


def format_warnings(findings: list[Finding]) -> list[str]:
    return [f"WARN: {f.message}" for f in findings]


def summarize_findings(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.kind] = counts.get(f.kind, 0) + 1
    return counts


def guard_validate_create(
    title: str,
    description: str,
    status: str,
    registry_path: Path,
    metadata: dict[str, str] | None = None,
) -> tuple[list[CreateViolation], dict[str, RegistryEntry] | None]:
    if not registry_path.is_file():
        raise FileNotFoundError(f"Registry file not found: {registry_path}")
    registry = parse_registry(registry_path)
    return validate_create(title, description, status, registry, metadata), registry


def epic_kind_hint(title: str, registry: dict[str, RegistryEntry]) -> str | None:
    """Return recommended domain_kind metadata value for epic titles."""
    match = EPIC_SLUG_RE.match((title or "").strip())
    if not match:
        return None
    entry = registry.get(match.group(1).strip())
    return entry.kind if entry else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only issue taxonomy linter (WARN-only, exit 0 on findings)"
    )
    parser.add_argument(
        "--json-file",
        type=Path,
        help="Fixture JSON (issues array or multica issue list response)",
    )
    parser.add_argument(
        "--registry-file",
        type=Path,
        default=DEFAULT_REGISTRY,
        help=f"Path to WORKSPACE_DOMAIN_REGISTRY.md (default: {DEFAULT_REGISTRY})",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Emit per-kind counts instead of per-finding lines",
    )
    parser.add_argument(
        "--guard",
        action="store_true",
        help="Blocking guard mode for guard-issue-create (exit 1 on violations)",
    )
    parser.add_argument("--title", help="Issue title (guard mode)")
    parser.add_argument("--description-file", type=Path, help="Description file (guard mode)")
    parser.add_argument("--status", default="backlog", help="Issue status (guard mode)")
    parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Metadata key=value for kind validation (guard mode; repeatable)",
    )
    args = parser.parse_args(argv)

    if args.guard:
        if not args.title or not args.description_file:
            print("ERROR: --guard requires --title and --description-file", file=sys.stderr)
            return 2
        if not args.description_file.is_file():
            print(f"ERROR: Description file not found: {args.description_file}", file=sys.stderr)
            return 2
        metadata = {}
        for item in args.metadata:
            if "=" not in item:
                print(f"ERROR: Invalid --metadata '{item}' (expected KEY=VALUE)", file=sys.stderr)
                return 2
            key, value = item.split("=", 1)
            metadata[key.strip()] = value.strip()
        try:
            violations, registry = guard_validate_create(
                args.title,
                args.description_file.read_text(encoding="utf-8"),
                args.status,
                args.registry_file.resolve(),
                metadata,
            )
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if violations:
            for v in violations:
                print(f"❌ BLOCKED [{v.gate}]: {v.message}", file=sys.stderr)
            return 1
        if registry:
            hint = epic_kind_hint(args.title, registry)
            if hint:
                print(
                    f"ℹ️ Post-create: multica issue metadata set <id> "
                    f"--key domain_kind --value {hint}",
                    file=sys.stderr,
                )
        return 0

    registry_path = args.registry_file.resolve()
    if not registry_path.is_file():
        print(f"ERROR: Registry file not found: {registry_path}", file=sys.stderr)
        return 1

    try:
        if args.json_file:
            if not args.json_file.is_file():
                print(f"ERROR: JSON file not found: {args.json_file}", file=sys.stderr)
                return 2
            issues = load_issues_from_json(args.json_file.read_text(encoding="utf-8"))
        else:
            issues = fetch_issues_via_cli()
        findings, _ = run_lint(issues, registry_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: Invalid issue JSON: {exc}", file=sys.stderr)
        return 2

    if not findings:
        return 0

    if args.brief:
        for kind, count in sorted(summarize_findings(findings).items()):
            print(f"WARN: {kind}: {count}")
    else:
        for line in format_warnings(findings):
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
