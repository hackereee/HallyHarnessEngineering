#!/usr/bin/env python3
"""
validate-state.py

校验 workflow-state.json：
  1. 通用结构 / 枚举 / 跨字段一致性 —— 走 JSON Schema（Draft 2020-12）。
  2. 跨文件一致性 —— activePlanRef 非空时 plan.md 与同目录 tasks.json 必须存在；
     L2/L3（activePlanRef 非空）执行阶段 activeTaskId 必须存在于对应 tasks.json；
     L0/L1（activePlanRef 为空）下 activeTaskId 必为 null，以 workflowId 作为审计锚点。
  3. 语义规则 —— workflow ownerRole、currentPhase 与 active task
     status / ownerRole 对齐；nextAction 的原子动作启发式检查。

任务等级与 state 形态对应（详见 .harness/rules/task-level.md）：
  L0 / direct-patch、L1 / verified-fix
      activePlanRef = null, activeTaskId = null, 锚点 = workflowId,
      当前责任角色 = workflow-state.ownerRole
  L2 / planned-task、L3 / decomposed-epic
      activePlanRef = "./plans/active/<PLAN-ID>/plan.md"
      activeTaskId  = tasks.json 中的某条 taskId（执行/测试/评审阶段）
      当前责任角色 = workflow-state.ownerRole，且必须与 active task ownerRole 对齐

退出码：
  0  校验通过
  1  校验失败（schema 或语义规则）
  2  运行错误（文件缺失 / JSON 解析失败 / 依赖缺失）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: 需要 jsonschema>=4.18，请执行 `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


# ---------- 基础工具 ----------

def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON 解析失败 {path}: {e}", file=sys.stderr)
        sys.exit(2)


# ---------- 1. Schema 校验 ----------

def validate_schema(state: dict, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(state), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"[schema] {loc}: {err.message}")
    return errors


# ---------- 2. 跨文件：activePlanRef 与 activeTaskId ∈ tasks.json ----------

def validate_active_plan_ref_exists(state: dict, state_path: Path) -> list[str]:
    plan_ref = state.get("activePlanRef")
    if not plan_ref:
        return []

    plan_file = (state_path.parent / plan_ref).resolve()
    if not plan_file.exists():
        return [f"[cross-file] activePlanRef 指向的 plan.md 不存在: {plan_file}"]
    if plan_file.name != "plan.md":
        return [f"[cross-file] activePlanRef 必须指向 plan.md: {plan_file}"]
    tasks_file = plan_file.parent / "tasks.json"
    if not tasks_file.exists():
        return [f"[cross-file] activePlanRef 所在目录缺少 tasks.json: {tasks_file}"]
    return []

def validate_active_task_exists(state: dict, state_path: Path) -> list[str]:
    active_task_id = state.get("activeTaskId")
    plan_ref = state.get("activePlanRef")

    # L0/L1：无 plan 且无 activeTaskId，workflowId 即锚点，跳过跨文件校验
    if active_task_id is None and not plan_ref:
        return []

    # L2/L3 在 planning / archiving 阶段：有 plan 但 activeTaskId 为 null，schema 已覆盖
    if active_task_id is None:
        return []

    # activeTaskId 非空但无 plan：L0/L1 约定 activeTaskId 必为 null，此组合非法
    if not plan_ref:
        return [
            "[cross-file] activeTaskId 非空但 activePlanRef 为空；"
            "L0/L1 任务请将 activeTaskId 置为 null，以 workflowId 作为锚点"
        ]

    plan_file = (state_path.parent / plan_ref).resolve()
    tasks_file = plan_file.parent / "tasks.json"
    if not tasks_file.exists():
        return [f"[cross-file] 未找到 tasks.json: {tasks_file}"]

    tasks = load_json(tasks_file)
    task_list = tasks.get("tasks", tasks if isinstance(tasks, list) else [])
    ids = {t.get("taskId") for t in task_list if isinstance(t, dict)}
    if active_task_id not in ids:
        return [f"[cross-file] activeTaskId={active_task_id!r} 不在 {tasks_file} 中"]
    return []


def load_active_task(state: dict, state_path: Path) -> tuple[Path, dict] | None:
    active_task_id = state.get("activeTaskId")
    plan_ref = state.get("activePlanRef")
    if active_task_id is None or not plan_ref:
        return None

    plan_file = (state_path.parent / plan_ref).resolve()
    tasks_file = plan_file.parent / "tasks.json"
    tasks = load_json(tasks_file)
    task_list = tasks.get("tasks", tasks if isinstance(tasks, list) else [])
    for task in task_list:
        if isinstance(task, dict) and task.get("taskId") == active_task_id:
            return tasks_file, task
    return None


_PHASE_TASK_EXPECTATIONS = {
    "implementing": ("implementing", "developer"),
    "testing": ("testing", "tester"),
    "reviewing": ("reviewing", "reviewer"),
}


def validate_active_task_phase_alignment(state: dict, state_path: Path) -> list[str]:
    phase = state.get("currentPhase")
    expected = _PHASE_TASK_EXPECTATIONS.get(phase)
    if expected is None:
        return []

    active_task_id = state.get("activeTaskId")
    plan_ref = state.get("activePlanRef")
    if active_task_id is None or not plan_ref:
        return []

    loaded = load_active_task(state, state_path)
    if loaded is None:
        return []

    tasks_file, task = loaded
    expected_status, expected_role = expected
    actual_status = task.get("status")
    actual_role = task.get("ownerRole")
    if actual_status == expected_status and actual_role == expected_role:
        return []

    return [
        "[cross-file] "
        f"currentPhase={phase!r} 要求 active task {active_task_id!r} "
        f"为 status={expected_status!r}, ownerRole={expected_role!r}；"
        f"但 {tasks_file} 中为 status={actual_status!r}, ownerRole={actual_role!r}"
    ]


def validate_active_task_owner_role_matches_state(state: dict, state_path: Path) -> list[str]:
    workflow_owner_role = state.get("ownerRole")
    active_task_id = state.get("activeTaskId")
    plan_ref = state.get("activePlanRef")
    if active_task_id is None or not plan_ref:
        return []

    loaded = load_active_task(state, state_path)
    if loaded is None:
        return []

    tasks_file, task = loaded
    task_owner_role = task.get("ownerRole")
    if workflow_owner_role == task_owner_role:
        return []

    return [
        "[cross-file] "
        f"workflow-state.ownerRole={workflow_owner_role!r} 必须等于 "
        f"active task {active_task_id!r} 的 ownerRole={task_owner_role!r}；"
        f"来源: {tasks_file}"
    ]


# ---------- 3. 语义：nextAction 原子性启发式 ----------

_MULTI_STEP_HINTS = (
    "然后", "接着", "之后", "再", "以及", "并且", "最后",
    " and ", " then ", ";", "；", "->", "→",
)
_VAGUE_HINTS = ("优化", "改进", "完善", "整理", "梳理", "设计整个", "规划整体")


def validate_next_action(state: dict) -> list[str]:
    action: str = state.get("nextAction", "").strip()
    if not action:
        return ["[semantic] nextAction 为空"]

    errors: list[str] = []
    low = action.lower()

    for hint in _MULTI_STEP_HINTS:
        if hint in action or hint in low:
            errors.append(f"[semantic] nextAction 疑似多步动作（命中 {hint!r}）：{action!r}")
            break

    if len(action) > 120:
        errors.append(f"[semantic] nextAction 过长({len(action)}字符)，可能不是原子动作")

    if re.match(r"^(优化|改进|完善|整理|梳理)", action):
        errors.append(f"[semantic] nextAction 疑似高层目标而非原子动作：{action!r}")

    for hint in _VAGUE_HINTS:
        if hint in action:
            errors.append(f"[semantic] nextAction 含模糊词 {hint!r}，建议改为可执行动作")
            break

    return errors


# ---------- 主流程 ----------

def run(state_path: Path, schema_path: Path) -> int:
    state = load_json(state_path)
    schema = load_json(schema_path)

    all_errors: list[str] = []
    all_errors += validate_schema(state, schema)
    all_errors += validate_active_plan_ref_exists(state, state_path)
    all_errors += validate_active_task_exists(state, state_path)
    all_errors += validate_active_task_phase_alignment(state, state_path)
    all_errors += validate_active_task_owner_role_matches_state(state, state_path)
    all_errors += validate_next_action(state)

    if all_errors:
        print(f"✗ {state_path} 校验失败（{len(all_errors)} 个问题）:")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print(f"✓ {state_path} 校验通过")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent  # .harness/scripts/ → repo root
    default_state = repo_root / ".harness" / "templates" / "workflow-state.template.json"
    default_schema = repo_root / ".harness" / "schemas" / "workflow-state.schema.json"

    parser = argparse.ArgumentParser(description="Validate workflow-state.json")
    parser.add_argument("--state", type=Path, default=default_state,
                        help="workflow-state.json 路径")
    parser.add_argument("--schema", type=Path, default=default_schema,
                        help="workflow-state.schema.json 路径")
    args = parser.parse_args(argv)
    return run(args.state, args.schema)


if __name__ == "__main__":
    sys.exit(main())
