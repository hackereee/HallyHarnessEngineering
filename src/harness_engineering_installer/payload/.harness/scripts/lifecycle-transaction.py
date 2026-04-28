#!/usr/bin/env python3
"""
lifecycle-transaction.py

Harness lifecycle 状态流转事务协调器。

职责：
  - 对一次 lifecycle transition 做 preflight / dry-run / commit / postflight。
  - 编排现有确定性网关：select-next-task.py、update-task.py、state-write.py。
  - 维护 handoff.md 的阶段交接摘要。

当前支持：
  - activate-next：从 planning 阶段激活第一个可执行 idle task。
  - start-testing：当前 implementing task 进入 testing gate。
  - start-review：当前 testing task 在验证通过后进入 reviewing gate。
  - review-failed：当前 reviewing task 在结构化 review failed 后回到 implementing。
  - review-passed：当前 reviewing task 在结构化 review passed 后标记 done，并激活下一个 task 或进入 archiving。

边界：
  - 不直接写 workflow-state.json。
  - 不手写 tasks.json 状态；task 状态变更必须经 update-task.py。
  - handoff.md 是恢复摘要，不是真相源。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class TransactionError(Exception):
    pass


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TransactionError(f"文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TransactionError(f"JSON 解析失败 {path}: {exc}") from exc


def script_path(root: Path, name: str) -> Path:
    return root / ".harness" / "scripts" / name


def state_path(root: Path) -> Path:
    return root / "work" / "workflow-state.json"


def workflow_schema(root: Path) -> Path:
    return root / ".harness" / "schemas" / "workflow-state.schema.json"


def tasks_schema(root: Path) -> Path:
    return root / ".harness" / "schemas" / "tasks.schema.json"


def active_plan_dir(root: Path, state: dict) -> Path:
    plan_ref = state.get("activePlanRef")
    if not isinstance(plan_ref, str):
        raise TransactionError("activePlanRef 为空；activate-next 需要 active plan")
    plan = (root / "work" / plan_ref).resolve()
    if plan.name != "plan.md":
        raise TransactionError(f"activePlanRef 必须指向 plan.md: {plan_ref}")
    return plan.parent


def run_checked(label: str, command: list[str], cwd: Path) -> str:
    rc, output = run_command(command, cwd)
    if rc != 0:
        raise TransactionError(f"{label} 失败:\n{output}")
    return output


def preflight(root: Path) -> dict:
    lint_output = run_checked(
        "preflight lint-harness.py",
        [sys.executable, str(script_path(root, "lint-harness.py")), "--root", str(root)],
        root,
    )
    validate_output = run_checked(
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
    return {"lint": lint_output, "validate": validate_output}


def postflight(root: Path) -> dict:
    lint_output = run_checked(
        "postflight lint-harness.py",
        [sys.executable, str(script_path(root, "lint-harness.py")), "--root", str(root)],
        root,
    )
    validate_output = run_checked(
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
    return {"lint": lint_output, "validate": validate_output}


def select_next_task(root: Path, plan_dir: Path) -> dict:
    output = run_checked(
        "select-next-task.py",
        [
            sys.executable,
            str(script_path(root, "select-next-task.py")),
            "--tasks",
            str(plan_dir / "tasks.json"),
            "--schema",
            str(tasks_schema(root)),
        ],
        root,
    )
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise TransactionError(f"select-next-task.py 输出不是合法 JSON:\n{output}") from exc


def load_tasks(plan_dir: Path) -> dict:
    return load_json(plan_dir / "tasks.json")


def find_task(manifest: dict, task_id: str) -> dict:
    for task in manifest.get("tasks", []):
        if isinstance(task, dict) and task.get("taskId") == task_id:
            return task
    raise TransactionError(f"activeTaskId 不在 tasks.json 中: {task_id}")


def active_task(root: Path, expected_phase: str, expected_status: str, expected_owner: str) -> tuple[dict, Path, dict]:
    state = load_json(state_path(root))
    if state.get("workflowStatus") != "active":
        raise TransactionError(
            f"{expected_phase} transition 只能用于 workflowStatus=active 的 workflow；"
            f"当前 workflowStatus={state.get('workflowStatus')}"
        )
    if state.get("currentPhase") != expected_phase:
        raise TransactionError(f"当前 phase 不是 {expected_phase}: {state.get('currentPhase')}")
    if state.get("ownerRole") != expected_owner:
        raise TransactionError(f"当前 ownerRole 不是 {expected_owner}: {state.get('ownerRole')}")
    task_id = state.get("activeTaskId")
    if not isinstance(task_id, str):
        raise TransactionError(f"{expected_phase} 阶段需要 activeTaskId")

    plan_dir = active_plan_dir(root, state)
    task = find_task(load_tasks(plan_dir), task_id)
    if task.get("status") != expected_status or task.get("ownerRole") != expected_owner:
        raise TransactionError(
            f"active task {task_id} 应为 status={expected_status}, ownerRole={expected_owner}；"
            f"实际为 status={task.get('status')}, ownerRole={task.get('ownerRole')}"
        )
    return state, plan_dir, task


def verification_has_evidence(task: dict) -> bool:
    verification = task.get("verification", {})
    return bool(verification.get("commands") or verification.get("checks"))


def ensure_verification_passed(task: dict) -> None:
    verification = task.get("verification", {})
    if verification.get("lastResult") != "passed":
        raise TransactionError(f"{task.get('taskId')} verification.lastResult 不是 passed")
    if not verification_has_evidence(task):
        raise TransactionError(f"{task.get('taskId')} 缺少 verification.commands 或 verification.checks")


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


def ensure_review_passed(task: dict) -> None:
    review = task.get("review", {})
    if review.get("lastResult") != "passed":
        raise TransactionError(f"{task.get('taskId')} review.lastResult 不是 passed")
    score = review.get("score")
    threshold = review.get("threshold")
    if not isinstance(score, int) or not isinstance(threshold, int):
        raise TransactionError(f"{task.get('taskId')} review.score/review.threshold 必须是整数")
    if score < threshold:
        raise TransactionError(f"{task.get('taskId')} review.score={score} 低于 threshold={threshold}")
    if not review.get("checks"):
        raise TransactionError(f"{task.get('taskId')} 缺少 review.checks")
    blockers = review_blockers(review)
    if blockers:
        raise TransactionError(f"{task.get('taskId')} 存在阻断 review findings: {'; '.join(blockers)}")


def ensure_review_failed(task: dict) -> None:
    review = task.get("review", {})
    if review.get("lastResult") != "failed":
        raise TransactionError(f"{task.get('taskId')} review.lastResult 不是 failed")
    if not review.get("checks") and not review.get("findings"):
        raise TransactionError(f"{task.get('taskId')} review failed 缺少 checks 或 findings")


def update_task(
    root: Path,
    plan_dir: Path,
    task_id: str,
    *,
    status: str,
    next_action: str,
    current_step: str,
) -> None:
    run_checked(
        "update-task.py",
        [
            sys.executable,
            str(script_path(root, "update-task.py")),
            "--tasks",
            str(plan_dir / "tasks.json"),
            "--schema",
            str(tasks_schema(root)),
            "--task",
            task_id,
            "--status",
            status,
            "--next-action",
            next_action,
            "--current-step",
            current_step,
        ],
        root,
    )


def update_task_for_activation(root: Path, plan_dir: Path, task_update: dict) -> None:
    update_task(
        root,
        plan_dir,
        task_update["taskId"],
        status=task_update["status"],
        next_action=task_update["nextAction"],
        current_step="Activated by lifecycle transaction",
    )


def write_state_patch(root: Path, patch: list[dict], *, source: str, reason: str) -> None:
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
            source,
            "--reason",
            reason,
        ],
        root,
    )


def append_handoff(
    plan_dir: Path,
    *,
    action: str,
    task_id: str,
    phase: str,
    role: str,
    next_action: str,
) -> None:
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    handoff_path = plan_dir / "handoff.md"
    with handoff_path.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n"
            f"## Lifecycle Transaction - {ts}\n\n"
            f"- action: {action}\n"
            f"- taskId: {task_id}\n"
            f"- phase: {phase}\n"
            f"- role: {role}\n"
            "- stateSource: workflow-state.json and tasks.json\n"
            f"- nextAction: {next_action}\n"
        )


def ensure_activate_next_preconditions(state: dict) -> None:
    if state.get("workflowStatus") != "active":
        raise TransactionError("activate-next 只能用于 workflowStatus=active 的 workflow")
    if state.get("currentPhase") != "planning":
        raise TransactionError("activate-next 只能从 currentPhase=planning 开始")
    if state.get("ownerRole") != "planner":
        raise TransactionError("activate-next 要求 workflow-state.ownerRole=planner")
    if state.get("activeTaskId") is not None:
        raise TransactionError("activate-next 要求 activeTaskId=null")


def execute_activate_next(root: Path) -> dict:
    preflight(root)
    state = load_json(state_path(root))
    ensure_activate_next_preconditions(state)
    plan_dir = active_plan_dir(root, state)
    selection = select_next_task(root, plan_dir)
    if selection.get("kind") != "task" or not selection.get("taskUpdate"):
        raise TransactionError("activate-next 需要 select-next-task.py 返回 kind=task")

    task_update = selection["taskUpdate"]
    update_task_for_activation(root, plan_dir, task_update)
    write_state_patch(
        root,
        selection["statePatch"],
        source="lifecycle-transaction.py",
        reason=f"activate-next {task_update['taskId']}",
    )
    append_handoff(
        plan_dir,
        action="activate-next",
        task_id=task_update["taskId"],
        phase="planning -> implementing",
        role="planner -> developer",
        next_action=task_update["nextAction"],
    )
    postflight(root)
    return {
        "action": "activate-next",
        "taskId": task_update["taskId"],
        "currentPhase": "implementing",
        "activeTaskId": task_update["taskId"],
        "nextAction": task_update["nextAction"],
    }


def execute_start_testing(root: Path) -> dict:
    preflight(root)
    state, plan_dir, task = active_task(root, "implementing", "implementing", "developer")
    task_id = task["taskId"]
    next_action = f"运行 {task_id} 验证"
    update_task(
        root,
        plan_dir,
        task_id,
        status="testing",
        next_action=next_action,
        current_step="Implementation ready for verification",
    )
    write_state_patch(
        root,
        [
            {"op": "replace", "path": "/currentPhase", "value": "testing"},
            {"op": "replace", "path": "/ownerRole", "value": "tester"},
            {"op": "replace", "path": "/activeTaskId", "value": task_id},
            {"op": "replace", "path": "/nextAction", "value": next_action},
        ],
        source="lifecycle-transaction.py",
        reason=f"start-testing {task_id}",
    )
    append_handoff(
        plan_dir,
        action="start-testing",
        task_id=task_id,
        phase="implementing -> testing",
        role="developer -> tester",
        next_action=next_action,
    )
    postflight(root)
    return {
        "action": "start-testing",
        "taskId": task_id,
        "currentPhase": "testing",
        "activeTaskId": state["activeTaskId"],
        "nextAction": next_action,
    }


def execute_start_review(root: Path) -> dict:
    preflight(root)
    state, plan_dir, task = active_task(root, "testing", "testing", "tester")
    ensure_verification_passed(task)
    task_id = task["taskId"]
    next_action = f"评审 {task_id} 交付结果"
    update_task(
        root,
        plan_dir,
        task_id,
        status="reviewing",
        next_action=next_action,
        current_step="Verification passed",
    )
    write_state_patch(
        root,
        [
            {"op": "replace", "path": "/currentPhase", "value": "reviewing"},
            {"op": "replace", "path": "/ownerRole", "value": "reviewer"},
            {"op": "replace", "path": "/activeTaskId", "value": task_id},
            {"op": "replace", "path": "/nextAction", "value": next_action},
        ],
        source="lifecycle-transaction.py",
        reason=f"start-review {task_id}",
    )
    append_handoff(
        plan_dir,
        action="start-review",
        task_id=task_id,
        phase="testing -> reviewing",
        role="tester -> reviewer",
        next_action=next_action,
    )
    postflight(root)
    return {
        "action": "start-review",
        "taskId": task_id,
        "currentPhase": "reviewing",
        "activeTaskId": state["activeTaskId"],
        "nextAction": next_action,
    }


def execute_review_failed(root: Path) -> dict:
    preflight(root)
    state, plan_dir, task = active_task(root, "reviewing", "reviewing", "reviewer")
    ensure_review_failed(task)
    task_id = task["taskId"]
    next_action = f"修正 {task_id} 的 review findings"
    update_task(
        root,
        plan_dir,
        task_id,
        status="implementing",
        next_action=next_action,
        current_step="Review failed",
    )
    write_state_patch(
        root,
        [
            {"op": "replace", "path": "/currentPhase", "value": "implementing"},
            {"op": "replace", "path": "/ownerRole", "value": "developer"},
            {"op": "replace", "path": "/activeTaskId", "value": task_id},
            {"op": "replace", "path": "/nextAction", "value": next_action},
        ],
        source="lifecycle-transaction.py",
        reason=f"review-failed {task_id}",
    )
    append_handoff(
        plan_dir,
        action="review-failed",
        task_id=task_id,
        phase="reviewing -> implementing",
        role="reviewer -> developer",
        next_action=next_action,
    )
    postflight(root)
    return {
        "action": "review-failed",
        "taskId": task_id,
        "currentPhase": "implementing",
        "activeTaskId": state["activeTaskId"],
        "nextAction": next_action,
    }


def execute_review_passed(root: Path) -> dict:
    preflight(root)
    state, plan_dir, task = active_task(root, "reviewing", "reviewing", "reviewer")
    ensure_verification_passed(task)
    ensure_review_passed(task)
    task_id = task["taskId"]
    update_task(
        root,
        plan_dir,
        task_id,
        status="done",
        next_action="",
        current_step="Review passed",
    )
    selection = select_next_task(root, plan_dir)
    if selection.get("kind") == "task":
        task_update = selection["taskUpdate"]
        update_task_for_activation(root, plan_dir, task_update)
        write_state_patch(
            root,
            selection["statePatch"],
            source="lifecycle-transaction.py",
            reason=f"review-passed {task_id}; activate {task_update['taskId']}",
        )
        append_handoff(
            plan_dir,
            action="review-passed",
            task_id=task_update["taskId"],
            phase="reviewing -> implementing",
            role="reviewer -> developer",
            next_action=task_update["nextAction"],
        )
        result_phase = "implementing"
        result_active = task_update["taskId"]
        result_next = task_update["nextAction"]
    elif selection.get("kind") == "archive":
        write_state_patch(
            root,
            selection["statePatch"],
            source="lifecycle-transaction.py",
            reason=f"review-passed {task_id}; archive plan",
        )
        result_next = "归档当前 plan package"
        append_handoff(
            plan_dir,
            action="review-passed",
            task_id=task_id,
            phase="reviewing -> archiving",
            role="reviewer -> developer",
            next_action=result_next,
        )
        result_phase = "archiving"
        result_active = None
    else:
        raise TransactionError("review-passed 需要 select-next-task.py 返回 kind=task 或 kind=archive")

    postflight(root)
    return {
        "action": "review-passed",
        "taskId": task_id,
        "currentPhase": result_phase,
        "activeTaskId": result_active,
        "previousActiveTaskId": state["activeTaskId"],
        "nextAction": result_next,
        "commitGate": {
            "required": True,
            "taskId": task_id,
            "command": f"python3 .harness/scripts/harness commit-task --task {task_id}",
            "timing": "after review-passed postflight and before new implementation work",
        },
    }


def copy_for_dry_run(root: Path, target: Path) -> Path:
    dry_root = target / "dry-run-root"
    shutil.copytree(root / ".harness", dry_root / ".harness")
    if (root / "work").exists():
        shutil.copytree(root / "work", dry_root / "work")
    return dry_root


def run_transaction(root: Path, action: str) -> dict:
    handlers = {
        "activate-next": execute_activate_next,
        "start-testing": execute_start_testing,
        "start-review": execute_start_review,
        "review-failed": execute_review_failed,
        "review-passed": execute_review_passed,
    }
    if action not in handlers:
        raise TransactionError(f"未知 action: {action}")

    # 先在隔离副本里跑完整事务，避免把可预见的跨工件失败带到真实 work/。
    with tempfile.TemporaryDirectory() as tmp:
        dry_root = copy_for_dry_run(root, Path(tmp))
        handlers[action](dry_root)

    return handlers[action](root)


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Coordinate Harness lifecycle artifact transitions")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument(
        "action",
        choices=("activate-next", "start-testing", "start-review", "review-failed", "review-passed"),
        help="Lifecycle transaction action",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = args.root.resolve()
    try:
        result = run_transaction(root, args.action)
    except TransactionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
