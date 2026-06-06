#!/usr/bin/env python3
"""
validate-state.py

Validate workflow-state.json:
  1. General structure, enums, and cross-field consistency through JSON Schema
     (Draft 2020-12).
  2. Cross-file consistency: when activePlanRef is non-null, plan.md and sibling
     tasks.json must exist; L2/L3 execution phases require activeTaskId to exist
     in that tasks.json; L0/L1 with activePlanRef null must keep activeTaskId
     null and use workflowId as the audit anchor.
  3. Semantic rules: workflow ownerRole/currentPhase must align with active task
     status/ownerRole; nextAction receives an atomic-action heuristic check.

Task level to state-shape mapping (see .harness/rules/task-level.md):
  L0 / direct-patch, L1 / verified-fix
      activePlanRef = null, activeTaskId = null, anchor = workflowId,
      current owner = workflow-state.ownerRole
  L2 / planned-task, L3 / decomposed-epic
      activePlanRef = "./plans/active/<PLAN-ID>/plan.md"
      activeTaskId = a taskId in tasks.json during implementing/testing/reviewing
      current owner = workflow-state.ownerRole and must align with active task ownerRole

Exit codes:
  0  validation passed
  1  validation failed (schema or semantic rules)
  2  runtime error (missing file / JSON parse failure / missing dependency)
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
    print("ERROR: jsonschema>=4.18 is required; run `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


# ---------- Basic Utilities ----------

def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON parse failed {path}: {e}", file=sys.stderr)
        sys.exit(2)


# ---------- 1. Schema Validation ----------

def validate_schema(state: dict, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(state), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"[schema] {loc}: {err.message}")
    return errors


# ---------- 2. Cross-file: activePlanRef and activeTaskId in tasks.json ----------

def validate_active_plan_ref_exists(state: dict, state_path: Path) -> list[str]:
    plan_ref = state.get("activePlanRef")
    if not plan_ref:
        return []

    plan_file = (state_path.parent / plan_ref).resolve()
    if not plan_file.exists():
        return [f"[cross-file] activePlanRef points to a missing plan.md: {plan_file}"]
    if plan_file.name != "plan.md":
        return [f"[cross-file] activePlanRef must point to plan.md: {plan_file}"]
    tasks_file = plan_file.parent / "tasks.json"
    if not tasks_file.exists():
        return [f"[cross-file] activePlanRef directory is missing tasks.json: {tasks_file}"]
    return []

def validate_active_task_exists(state: dict, state_path: Path) -> list[str]:
    active_task_id = state.get("activeTaskId")
    plan_ref = state.get("activePlanRef")

    # L0/L1: no plan and no activeTaskId; workflowId is the anchor, so skip cross-file checks.
    if active_task_id is None and not plan_ref:
        return []

    # L2/L3 in planning/archiving: plan exists but activeTaskId is null; schema covers this.
    if active_task_id is None:
        return []

    # Non-null activeTaskId without a plan: illegal because L0/L1 must keep activeTaskId null.
    if not plan_ref:
        return [
            "[cross-file] activeTaskId is non-null while activePlanRef is null; "
            "L0/L1 work must set activeTaskId to null and use workflowId as the anchor"
        ]

    plan_file = (state_path.parent / plan_ref).resolve()
    tasks_file = plan_file.parent / "tasks.json"
    if not tasks_file.exists():
        return [f"[cross-file] tasks.json not found: {tasks_file}"]

    tasks = load_json(tasks_file)
    task_list = tasks.get("tasks", tasks if isinstance(tasks, list) else [])
    ids = {t.get("taskId") for t in task_list if isinstance(t, dict)}
    if active_task_id not in ids:
        return [f"[cross-file] activeTaskId={active_task_id!r} is not in {tasks_file}"]
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
        f"currentPhase={phase!r} requires active task {active_task_id!r} "
        f"to have status={expected_status!r}, ownerRole={expected_role!r}; "
        f"but {tasks_file} has status={actual_status!r}, ownerRole={actual_role!r}"
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
        f"workflow-state.ownerRole={workflow_owner_role!r} must equal "
        f"active task {active_task_id!r} ownerRole={task_owner_role!r}; "
        f"source: {tasks_file}"
    ]


# ---------- 3. Semantic: nextAction Atomicity Heuristic ----------

_MULTI_STEP_HINTS = (
    " and ", " then ", " after that ", " and then ", " finally ", ";", "->",
)
_VAGUE_HINTS = ("optimize", "improve", "polish", "clean up", "organize", "design the whole", "plan the whole")


def validate_next_action(state: dict) -> list[str]:
    action: str = state.get("nextAction", "").strip()
    if not action:
        return ["[semantic] nextAction is empty"]

    errors: list[str] = []
    low = action.lower()

    for hint in _MULTI_STEP_HINTS:
        if hint in action or hint in low:
            errors.append(f"[semantic] nextAction appears to contain multiple steps (matched {hint!r}): {action!r}")
            break

    if len(action) > 120:
        errors.append(f"[semantic] nextAction is too long ({len(action)} chars) and may not be atomic")

    if re.match(r"^(optimize|improve|polish|clean up|organize)\b", low):
        errors.append(f"[semantic] nextAction appears to be a high-level goal rather than an atomic action: {action!r}")

    for hint in _VAGUE_HINTS:
        if hint in low:
            errors.append(f"[semantic] nextAction contains vague wording {hint!r}; use an executable action")
            break

    return errors


# ---------- Main Flow ----------

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
        print(f"✗ {state_path} validation failed ({len(all_errors)} issue(s)):")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print(f"✓ {state_path} validation passed")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent  # .harness/scripts/ -> repo root
    default_state = repo_root / ".harness" / "templates" / "workflow-state.template.json"
    default_schema = repo_root / ".harness" / "schemas" / "workflow-state.schema.json"

    parser = argparse.ArgumentParser(description="Validate workflow-state.json")
    parser.add_argument("--state", type=Path, default=default_state,
                        help="workflow-state.json path")
    parser.add_argument("--schema", type=Path, default=default_schema,
                        help="workflow-state.schema.json path")
    args = parser.parse_args(argv)
    return run(args.state, args.schema)


if __name__ == "__main__":
    sys.exit(main())
