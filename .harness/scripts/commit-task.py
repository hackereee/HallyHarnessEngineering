#!/usr/bin/env python3
"""
commit-task.py

Commit a completed Harness task after review-passed and before new delivery work starts.

Responsibilities:
  - Read workflow-state.json and the current active plan's tasks.json.
  - Confirm the target task is done and verification/review gates both passed.
  - Allow the same commit to include state changes that activate the next task.
  - Create the task completion commit through git add -A / git commit.

Boundary:
  - Do not write workflow-state.json or tasks.json.
  - Do not replace lifecycle-transaction.py state transitions.
  - Do not model commit as a task.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


class CommitTaskError(Exception):
    pass


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def run_checked(label: str, command: list[str], cwd: Path) -> str:
    rc, output = run_command(command, cwd)
    if rc != 0:
        raise CommitTaskError(f"{label} failed:\n{output}")
    return output


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CommitTaskError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CommitTaskError(f"JSON parse failed {path}: {exc}") from exc


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def state_path(root: Path) -> Path:
    return root / "work" / "workflow-state.json"


def active_plan_dir(root: Path, state: dict) -> Path:
    plan_ref = state.get("activePlanRef")
    if not isinstance(plan_ref, str):
        raise CommitTaskError("activePlanRef is empty; commit-task requires an active plan")
    plan_path = (root / "work" / plan_ref).resolve()
    if plan_path.name != "plan.md":
        raise CommitTaskError(f"activePlanRef must point to plan.md: {plan_ref}")
    if not plan_path.exists():
        raise CommitTaskError(f"activePlanRef points to a missing plan.md: {plan_path}")
    return plan_path.parent


def find_task(manifest: dict, task_id: str) -> dict:
    for task in manifest.get("tasks", []):
        if isinstance(task, dict) and task.get("taskId") == task_id:
            return task
    raise CommitTaskError(f"taskId is not in tasks.json: {task_id}")


def review_blockers(review: dict) -> list[str]:
    blockers: list[str] = []
    for finding in review.get("findings", []):
        if not isinstance(finding, dict):
            continue
        severity = finding.get("severity")
        blocking = finding.get("blocking")
        summary = finding.get("summary", "<missing summary>")
        if severity == "critical":
            blockers.append(f"critical: {summary}")
        elif severity == "important" and blocking is True:
            blockers.append(f"blocking important: {summary}")
    return blockers


def ensure_task_committable(task: dict) -> None:
    task_id = task.get("taskId")
    if task.get("status") != "done":
        raise CommitTaskError(f"{task_id} status is not done: {task.get('status')}")

    verification = task.get("verification", {})
    if verification.get("lastResult") != "passed":
        raise CommitTaskError(f"{task_id} verification.lastResult is not passed")
    if not verification.get("commands") and not verification.get("checks"):
        raise CommitTaskError(f"{task_id} is missing verification.commands or verification.checks")

    review = task.get("review", {})
    if review.get("lastResult") != "passed":
        raise CommitTaskError(f"{task_id} review.lastResult is not passed")
    if not review.get("checks"):
        raise CommitTaskError(f"{task_id} is missing review.checks")

    score = review.get("score")
    threshold = review.get("threshold")
    if not isinstance(score, int) or not isinstance(threshold, int):
        raise CommitTaskError(f"{task_id} review.score/review.threshold must be integers")
    if score < threshold:
        raise CommitTaskError(f"{task_id} review.score={score} is below threshold={threshold}")

    blockers = review_blockers(review)
    if blockers:
        raise CommitTaskError(f"{task_id} has blocking review findings: {'; '.join(blockers)}")


def ensure_active_workflow(state: dict) -> None:
    if state.get("workflowStatus") != "active":
        raise CommitTaskError(f"workflowStatus is not active: {state.get('workflowStatus')}")
    if state.get("currentPhase") not in {"implementing", "archiving"}:
        raise CommitTaskError(
            "commit-task must run after review-passed and before the next new implementation; "
            f"current currentPhase={state.get('currentPhase')}"
        )


def default_message(task: dict) -> str:
    title = task.get("title")
    if isinstance(title, str) and title.strip():
        return f"Complete {task.get('taskId')}: {title.strip()}"
    return f"Complete {task.get('taskId')}"


def git_root_for(root: Path) -> Path:
    top_level = run_checked("git rev-parse", ["git", "rev-parse", "--show-toplevel"], root)
    git_root = Path(top_level).resolve()
    try:
        root.resolve().relative_to(git_root)
    except ValueError as exc:
        raise CommitTaskError(f"--root is not inside a Git worktree: {root}") from exc
    return git_root


def git_commit(root: Path, task: dict, message: str) -> dict:
    git_root = git_root_for(root)
    status = run_checked("git status", ["git", "status", "--porcelain"], git_root)
    if not status:
        raise CommitTaskError("no changes to commit")

    run_checked("git add", ["git", "add", "-A"], git_root)
    staged = run_checked("git diff --cached", ["git", "diff", "--cached", "--name-only"], git_root)
    if not staged:
        raise CommitTaskError("no staged changes to commit")
    paths = sorted(line for line in staged.splitlines() if line)

    run_checked("git commit", ["git", "commit", "-m", message], git_root)
    commit = run_checked("git rev-parse", ["git", "rev-parse", "--short", "HEAD"], git_root)
    return {
        "action": "commit-task",
        "taskId": task.get("taskId"),
        "message": message,
        "commit": commit,
        "paths": paths,
    }


def run(root: Path, task_id: str, message: str | None) -> dict:
    root = git_root_for(root)
    state = load_json(state_path(root))
    if not isinstance(state, dict):
        raise CommitTaskError("workflow-state.json top-level JSON must be an object")
    ensure_active_workflow(state)

    plan_dir = active_plan_dir(root, state)
    manifest = load_json(plan_dir / "tasks.json")
    if not isinstance(manifest, dict):
        raise CommitTaskError(f"{rel(plan_dir / 'tasks.json', root)} top-level JSON must be an object")
    task = find_task(manifest, task_id)
    ensure_task_committable(task)

    return git_commit(root, task, message or default_message(task))


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Commit a completed Harness task")
    parser.add_argument("--root", type=Path, default=repo_root, help="Path inside repository; normalized to Git top-level")
    parser.add_argument("--task", required=True, help="Completed task ID, e.g. TASK-001")
    parser.add_argument("--message", help="Override commit message")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = run(args.root.resolve(), args.task, args.message)
    except CommitTaskError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
