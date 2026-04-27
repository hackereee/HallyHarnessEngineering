#!/usr/bin/env python3
"""
complete-workflow.py

收口无 active plan 的 L0/L1 workflow。

边界：
  - 只适用于 activePlanRef=null 且 activeTaskId=null 的直接 workflow。
  - 不迁移 plan package；L2/L3 必须继续走 archive-plan.py。
  - completion evidence 写入 session 审计 JSONL。
  - workflow-state.json 的写入仍通过 state-write.py。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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
        raise CompleteWorkflowError(f"{label} 失败:\n{output}")
    return output


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CompleteWorkflowError(f"文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CompleteWorkflowError(f"JSON 解析失败 {path}: {exc}") from exc


def parse_timestamp(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc).astimezone()
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CompleteWorkflowError(f"--timestamp 不是合法 ISO 8601 时间: {raw}") from exc
    if parsed.tzinfo is None:
        raise CompleteWorkflowError("--timestamp 必须包含时区，例如 2026-04-27T09:00:00+08:00")
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
        raise CompleteWorkflowError("complete-workflow 只能用于 workflowStatus=active 的 workflow")
    if state.get("activePlanRef") is not None or state.get("activeTaskId") is not None:
        raise CompleteWorkflowError("complete-workflow 只适用于 L0/L1；L2/L3 请使用 archive-plan.py")
    dirs = active_plan_dirs(root)
    if dirs:
        names = ", ".join(path.name for path in dirs)
        raise CompleteWorkflowError(f"complete-workflow 只适用于 L0/L1；仍存在 active plan: {names}")
    if state.get("currentPhase") != "reviewing" or state.get("ownerRole") != "reviewer":
        raise CompleteWorkflowError("complete-workflow 要求 currentPhase=reviewing 且 ownerRole=reviewer")


def ensure_evidence(args: argparse.Namespace) -> None:
    if not args.verification_command and not args.verification_check:
        raise CompleteWorkflowError("完成 L0/L1 workflow 前必须提供 verification command 或 check")
    if not args.review_summary.strip():
        raise CompleteWorkflowError("--review-summary 不能为空")


def write_state_completed(root: Path) -> None:
    patch = [
        {"op": "replace", "path": "/workflowStatus", "value": "completed"},
        {"op": "replace", "path": "/activePlanRef", "value": None},
        {"op": "replace", "path": "/activeTaskId", "value": None},
        {"op": "replace", "path": "/nextAction", "value": "开启下一个 workflow"},
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
        ],
        root,
    )


def append_completion_audit(root: Path, timestamp: datetime, before: dict, args: argparse.Namespace) -> Path:
    audit_path = root / "work" / "sessions" / timestamp.date().isoformat() / "workflow-completions.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
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
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return audit_path


def complete(root: Path, args: argparse.Namespace) -> dict:
    timestamp = parse_timestamp(args.timestamp)
    ensure_evidence(args)
    preflight(root)

    before = load_json(state_path(root))
    if not isinstance(before, dict):
        raise CompleteWorkflowError("workflow-state.json 顶层必须是对象")
    ensure_direct_completion_preconditions(root, before)

    write_state_completed(root)
    audit_path = append_completion_audit(root, timestamp, before, args)
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
