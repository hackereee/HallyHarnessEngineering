#!/usr/bin/env python3
"""
commit-task.py

Commit a completed Harness task after review-passed and before new delivery work starts.

职责：
  - 读取 workflow-state.json 和当前 active plan 的 tasks.json。
  - 确认目标 task 已 done，verification/review gate 均 passed。
  - 允许同一次提交包含激活下一个 task 的状态变更。
  - 通过 git add -A / git commit 生成任务完成提交。

边界：
  - 不写 workflow-state.json 或 tasks.json。
  - 不替代 lifecycle-transaction.py 的状态流转。
  - 不把 commit 建模成 task。
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
        raise CommitTaskError(f"{label} 失败:\n{output}")
    return output


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CommitTaskError(f"文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CommitTaskError(f"JSON 解析失败 {path}: {exc}") from exc


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
        raise CommitTaskError("activePlanRef 为空；commit-task 需要 active plan")
    plan_path = (root / "work" / plan_ref).resolve()
    if plan_path.name != "plan.md":
        raise CommitTaskError(f"activePlanRef 必须指向 plan.md: {plan_ref}")
    if not plan_path.exists():
        raise CommitTaskError(f"activePlanRef 指向的 plan.md 不存在: {plan_path}")
    return plan_path.parent


def find_task(manifest: dict, task_id: str) -> dict:
    for task in manifest.get("tasks", []):
        if isinstance(task, dict) and task.get("taskId") == task_id:
            return task
    raise CommitTaskError(f"taskId 不在 tasks.json 中: {task_id}")


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
        raise CommitTaskError(f"{task_id} status 不是 done: {task.get('status')}")

    verification = task.get("verification", {})
    if verification.get("lastResult") != "passed":
        raise CommitTaskError(f"{task_id} verification.lastResult 不是 passed")
    if not verification.get("commands") and not verification.get("checks"):
        raise CommitTaskError(f"{task_id} 缺少 verification.commands 或 verification.checks")

    review = task.get("review", {})
    if review.get("lastResult") != "passed":
        raise CommitTaskError(f"{task_id} review.lastResult 不是 passed")
    if not review.get("checks"):
        raise CommitTaskError(f"{task_id} 缺少 review.checks")

    score = review.get("score")
    threshold = review.get("threshold")
    if not isinstance(score, int) or not isinstance(threshold, int):
        raise CommitTaskError(f"{task_id} review.score/review.threshold 必须是整数")
    if score < threshold:
        raise CommitTaskError(f"{task_id} review.score={score} 低于 threshold={threshold}")

    blockers = review_blockers(review)
    if blockers:
        raise CommitTaskError(f"{task_id} 存在阻断 review findings: {'; '.join(blockers)}")


def ensure_active_workflow(state: dict) -> None:
    if state.get("workflowStatus") != "active":
        raise CommitTaskError(f"workflowStatus 不是 active: {state.get('workflowStatus')}")
    if state.get("currentPhase") not in {"implementing", "archiving"}:
        raise CommitTaskError(
            "commit-task 必须在 review-passed 之后、下一轮新实现之前运行；"
            f"当前 currentPhase={state.get('currentPhase')}"
        )


def default_message(task: dict) -> str:
    title = task.get("title")
    if isinstance(title, str) and title.strip():
        return f"完成 {task.get('taskId')}: {title.strip()}"
    return f"完成 {task.get('taskId')}"


def ensure_git_root(root: Path) -> None:
    top_level = run_checked("git rev-parse", ["git", "rev-parse", "--show-toplevel"], root)
    if Path(top_level).resolve() != root.resolve():
        raise CommitTaskError(f"--root 必须是 Git 顶层目录: {root}")


def git_commit(root: Path, task: dict, message: str) -> dict:
    ensure_git_root(root)
    status = run_checked("git status", ["git", "status", "--porcelain"], root)
    if not status:
        raise CommitTaskError("没有可提交的变更")

    run_checked("git add", ["git", "add", "-A"], root)
    staged = run_checked("git diff --cached", ["git", "diff", "--cached", "--name-only"], root)
    if not staged:
        raise CommitTaskError("没有可提交的 staged 变更")
    paths = sorted(line for line in staged.splitlines() if line)

    run_checked("git commit", ["git", "commit", "-m", message], root)
    commit = run_checked("git rev-parse", ["git", "rev-parse", "--short", "HEAD"], root)
    return {
        "action": "commit-task",
        "taskId": task.get("taskId"),
        "message": message,
        "commit": commit,
        "paths": paths,
    }


def run(root: Path, task_id: str, message: str | None) -> dict:
    state = load_json(state_path(root))
    if not isinstance(state, dict):
        raise CommitTaskError("workflow-state.json 顶层必须是对象")
    ensure_active_workflow(state)

    plan_dir = active_plan_dir(root, state)
    manifest = load_json(plan_dir / "tasks.json")
    if not isinstance(manifest, dict):
        raise CommitTaskError(f"{rel(plan_dir / 'tasks.json', root)} 顶层必须是对象")
    task = find_task(manifest, task_id)
    ensure_task_committable(task)

    return git_commit(root, task, message or default_message(task))


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Commit a completed Harness task")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
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
