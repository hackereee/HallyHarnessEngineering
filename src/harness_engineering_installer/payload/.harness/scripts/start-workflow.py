#!/usr/bin/env python3
"""
start-workflow.py

从 completed / archived 终态开启一个新的 Harness workflow。

边界：
  - 只允许旧 workflow 已处于终态，且不再持有 active plan / active task。
  - 不直接写 workflow-state.json；真实写入仍通过 state-write.py。
  - direct workflow（L0/L1）进入 implementing/developer。
  - planned workflow（L2/L3）绑定已存在的 active plan package，进入 planning/planner。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


TERMINAL_STATUSES = {"completed", "archived"}
DIRECT_LEVELS = {"L0", "L1"}
PLANNED_LEVELS = {"L2", "L3"}


class StartWorkflowError(Exception):
    pass


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def run_checked(label: str, command: list[str], cwd: Path) -> str:
    rc, output = run_command(command, cwd)
    if rc != 0:
        raise StartWorkflowError(f"{label} 失败:\n{output}")
    return output


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StartWorkflowError(f"文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StartWorkflowError(f"JSON 解析失败 {path}: {exc}") from exc


def script_path(root: Path, name: str) -> Path:
    return root / ".harness" / "scripts" / name


def state_path(root: Path) -> Path:
    return root / "work" / "workflow-state.json"


def workflow_schema(root: Path) -> Path:
    return root / ".harness" / "schemas" / "workflow-state.schema.json"


def validate_state(root: Path) -> None:
    run_checked(
        "validate-state.py",
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


def lint_harness(root: Path) -> None:
    run_checked(
        "lint-harness.py",
        [sys.executable, str(script_path(root, "lint-harness.py")), "--root", str(root)],
        root,
    )


def ensure_terminal_state(state: dict) -> None:
    if state.get("workflowStatus") not in TERMINAL_STATUSES:
        raise StartWorkflowError("start-workflow 只能从 completed/archived 终态开启新 workflow")
    if state.get("activePlanRef") is not None or state.get("activeTaskId") is not None:
        raise StartWorkflowError("终态 workflow 不应持有 activePlanRef 或 activeTaskId")


def validate_args(args: argparse.Namespace) -> None:
    if args.level in DIRECT_LEVELS and args.plan_ref:
        raise StartWorkflowError("L0/L1 direct workflow 不允许传入 --plan-ref")
    if args.level in PLANNED_LEVELS and not args.plan_ref:
        raise StartWorkflowError("L2/L3 planned workflow 必须传入 --plan-ref")


def patch_for(args: argparse.Namespace) -> list[dict]:
    if args.level in DIRECT_LEVELS:
        active_plan_ref: str | None = None
        current_phase = "implementing"
        owner_role = "developer"
    else:
        active_plan_ref = args.plan_ref
        current_phase = "planning"
        owner_role = "planner"

    return [
        {"op": "replace", "path": "/workflowId", "value": args.workflow_id},
        {"op": "replace", "path": "/workflowStatus", "value": "active"},
        {"op": "replace", "path": "/activePlanRef", "value": active_plan_ref},
        {"op": "replace", "path": "/activeTaskId", "value": None},
        {"op": "replace", "path": "/currentPhase", "value": current_phase},
        {"op": "replace", "path": "/ownerRole", "value": owner_role},
        {"op": "replace", "path": "/nextAction", "value": args.next_action},
    ]


def write_state(root: Path, patch: list[dict], workflow_id: str) -> None:
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
            "start-workflow.py",
            "--reason",
            f"start workflow {workflow_id}",
            "--allow-terminal-reset",
        ],
        root,
    )


def copy_for_dry_run(root: Path, target: Path) -> Path:
    dry_root = target / "dry-run-root"
    shutil.copytree(root / ".harness", dry_root / ".harness")
    if (root / "work").exists():
        shutil.copytree(root / "work", dry_root / "work")
    return dry_root


def execute_once(root: Path, patch: list[dict], workflow_id: str) -> None:
    write_state(root, patch, workflow_id)
    lint_harness(root)
    validate_state(root)


def start_workflow(root: Path, args: argparse.Namespace) -> dict:
    validate_args(args)
    validate_state(root)
    state = load_json(state_path(root))
    if not isinstance(state, dict):
        raise StartWorkflowError("workflow-state.json 顶层必须是对象")
    ensure_terminal_state(state)

    patch = patch_for(args)

    # 在隔离副本里先跑完整写入与 postflight。planned workflow 允许 active plan
    # package 先落盘、再由本脚本绑定到新 state；真实工作区在 dry-run 成功后才写入。
    with tempfile.TemporaryDirectory() as tmp:
        dry_root = copy_for_dry_run(root, Path(tmp))
        execute_once(dry_root, patch, args.workflow_id)

    execute_once(root, patch, args.workflow_id)
    new_state = load_json(state_path(root))
    return {
        "workflowId": new_state["workflowId"],
        "workflowStatus": new_state["workflowStatus"],
        "currentPhase": new_state["currentPhase"],
        "ownerRole": new_state["ownerRole"],
        "activePlanRef": new_state["activePlanRef"],
        "activeTaskId": new_state["activeTaskId"],
        "nextAction": new_state["nextAction"],
    }


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Start a new Harness workflow from a terminal workflow state")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument("--level", choices=("L0", "L1", "L2", "L3"), required=True, help="Harness task level")
    parser.add_argument("--workflow-id", required=True, help="New workflowId")
    parser.add_argument("--next-action", required=True, help="Atomic nextAction for the new workflow")
    parser.add_argument("--plan-ref", help="Required for L2/L3, e.g. ./plans/active/PLAN-002/plan.md")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = start_workflow(args.root.resolve(), args)
    except StartWorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (OSError, shutil.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
