#!/usr/bin/env python3
"""
complete-workflow.py

Close an L0/L1 workflow that has no active plan.

Boundary:
  - Applies only to direct workflows with activePlanRef=null and activeTaskId=null.
  - Does not migrate a plan package; L2/L3 must continue through archive-plan.py.
  - Writes completion evidence to the session audit JSONL.
  - workflow-state.json writes still go through state-write.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class CompleteWorkflowError(Exception):
    pass


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def run_checked(label: str, command: list[str], cwd: Path) -> str:
    rc, output = run_command(command, cwd)
    if rc != 0:
        raise CompleteWorkflowError(f"{label} failed:\n{output}")
    return output


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CompleteWorkflowError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CompleteWorkflowError(f"JSON parse failed {path}: {exc}") from exc


def parse_timestamp(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc).astimezone()
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CompleteWorkflowError(f"--timestamp is not valid ISO 8601: {raw}") from exc
    if parsed.tzinfo is None:
        raise CompleteWorkflowError("--timestamp must include a timezone, for example 2026-04-27T09:00:00+08:00")
    return parsed


def format_timestamp(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def script_path(root: Path, name: str) -> Path:
    return root / ".harness" / "scripts" / name


def state_path(root: Path) -> Path:
    return root / "work" / "workflow-state.json"


def workflow_schema(root: Path) -> Path:
    return root / ".harness" / "schemas" / "workflow-state.schema.json"


def active_plan_dirs(root: Path) -> list[Path]:
    active_root = root / "work" / "plans" / "active"
    if not active_root.exists() or not active_root.is_dir():
        return []
    return sorted(path for path in active_root.iterdir() if path.is_dir())


def preflight(root: Path) -> None:
    run_checked(
        "preflight lint-harness.py",
        [sys.executable, str(script_path(root, "lint-harness.py")), "--root", str(root)],
        root,
    )
    run_checked(
        "preflight validate-state.py",
        [
            sys.executable,
            str(script_path(root, "validate-state.py")),
            "--state",
            str(state_path(root)),
            "--schema",
            str(workflow_schema(root)),
        ],
        root,
    )


def postflight(root: Path) -> None:
    run_checked(
        "postflight lint-harness.py",
        [sys.executable, str(script_path(root, "lint-harness.py")), "--root", str(root)],
        root,
    )
    run_checked(
        "postflight validate-state.py",
        [
            sys.executable,
            str(script_path(root, "validate-state.py")),
            "--state",
            str(state_path(root)),
            "--schema",
            str(workflow_schema(root)),
        ],
        root,
    )


def ensure_direct_completion_preconditions(root: Path, state: dict) -> None:
    if state.get("workflowStatus") != "active":
        raise CompleteWorkflowError("complete-workflow can only run on workflowStatus=active")
    if state.get("activePlanRef") is not None or state.get("activeTaskId") is not None:
        raise CompleteWorkflowError("complete-workflow applies only to L0/L1; use archive-plan.py for L2/L3")
    dirs = active_plan_dirs(root)
    if dirs:
        names = ", ".join(path.name for path in dirs)
        raise CompleteWorkflowError(f"complete-workflow applies only to L0/L1; active plans still exist: {names}")
    if state.get("currentPhase") != "reviewing" or state.get("ownerRole") != "reviewer":
        raise CompleteWorkflowError("complete-workflow requires currentPhase=reviewing and ownerRole=reviewer")


def ensure_evidence(args: argparse.Namespace) -> None:
    if not args.verification_command and not args.verification_check:
        raise CompleteWorkflowError("before completing an L0/L1 workflow, provide a verification command or check")
    if not args.review_summary.strip():
        raise CompleteWorkflowError("--review-summary must not be empty")
    if not args.architecture_impact.strip():
        raise CompleteWorkflowError("--architecture-impact must not be empty; record the architecture impact judgment")


def write_state_completed(root: Path) -> None:
    patch = [
        {"op": "replace", "path": "/workflowStatus", "value": "completed"},
        {"op": "replace", "path": "/activePlanRef", "value": None},
        {"op": "replace", "path": "/activeTaskId", "value": None},
        {"op": "replace", "path": "/nextAction", "value": "Start next workflow"},
    ]
    run_checked(
        "state-write.py",
        [
            sys.executable,
            str(script_path(root, "state-write.py")),
            "--state",
            str(state_path(root)),
            "--schema",
            str(workflow_schema(root)),
            "--validator",
            str(script_path(root, "validate-state.py")),
            "--patch-json",
            json.dumps(patch, ensure_ascii=False),
            "--source",
            "complete-workflow.py",
            "--reason",
            "complete L0/L1 workflow",
            "--allow-terminal-close",
        ],
        root,
    )


def completion_audit_path(root: Path, timestamp: datetime) -> Path:
    return root / "work" / "sessions" / timestamp.date().isoformat() / "workflow-completions.jsonl"


def completion_audit_entry(timestamp: datetime, before: dict, args: argparse.Namespace) -> dict:
    return {
        "ts": format_timestamp(timestamp),
        "workflowId": before.get("workflowId"),
        "workflowStatus": "completed",
        "levelShape": "L0/L1",
        "stateSource": "work/workflow-state.json",
        "verification": {
            "commands": args.verification_command,
            "checks": args.verification_check,
        },
        "reviewSummary": args.review_summary.strip(),
        "architectureImpact": args.architecture_impact.strip(),
    }


def ensure_completion_audit_writable(audit_path: Path) -> None:
    if audit_path.exists() and audit_path.is_dir():
        raise CompleteWorkflowError(f"completion audit path is a directory: {audit_path}")
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=audit_path.name + ".", suffix=".tmp", dir=audit_path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("")
            handle.flush()
            os.fsync(handle.fileno())
        os.unlink(tmp_name)
    except OSError as exc:
        raise CompleteWorkflowError(f"completion audit is not writable: {audit_path}: {exc}") from exc


def atomic_append_jsonl(audit_path: Path, entry: dict) -> None:
    ensure_completion_audit_writable(audit_path)
    existing = ""
    if audit_path.exists():
        existing = audit_path.read_text(encoding="utf-8")
    if existing and not existing.endswith("\n"):
        existing += "\n"
    next_content = existing + json.dumps(entry, ensure_ascii=False) + "\n"

    fd, tmp_name = tempfile.mkstemp(prefix=audit_path.name + ".", suffix=".tmp", dir=audit_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(next_content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, audit_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def append_completion_audit(audit_path: Path, entry: dict) -> Path:
    atomic_append_jsonl(audit_path, entry)
    return audit_path


def complete(root: Path, args: argparse.Namespace) -> dict:
    timestamp = parse_timestamp(args.timestamp)
    ensure_evidence(args)
    preflight(root)

    before = load_json(state_path(root))
    if not isinstance(before, dict):
        raise CompleteWorkflowError("workflow-state.json top-level JSON must be an object")
    ensure_direct_completion_preconditions(root, before)
    audit_path = completion_audit_path(root, timestamp)
    entry = completion_audit_entry(timestamp, before, args)
    ensure_completion_audit_writable(audit_path)

    write_state_completed(root)
    audit_path = append_completion_audit(audit_path, entry)
    postflight(root)
    return {
        "action": "complete-workflow",
        "workflowId": before.get("workflowId"),
        "workflowStatus": "completed",
        "audit": str(audit_path),
    }


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Complete an L0/L1 Harness workflow")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument("--timestamp", help="ISO 8601 timestamp with timezone")
    parser.add_argument(
        "--verification-command",
        action="append",
        default=[],
        help="Verification command supporting completion; repeatable",
    )
    parser.add_argument(
        "--verification-check",
        action="append",
        default=[],
        help="Manual or structural verification check supporting completion; repeatable",
    )
    parser.add_argument("--review-summary", required=True, help="Reviewer summary for session audit")
    parser.add_argument(
        "--architecture-impact",
        default="",
        help="Architecture impact summary for root ARCHITECTURE.md and Harness framework architecture",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = complete(args.root.resolve(), args)
    except CompleteWorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
