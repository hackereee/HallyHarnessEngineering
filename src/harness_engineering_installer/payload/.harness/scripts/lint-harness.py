#!/usr/bin/env python3
"""
lint-harness.py

Directory-level Harness invariant inspection. It is a lifecycle preflight /
postflight gate, not a workflow phase. It is read-only and does not write
workflow-state.json or tasks.json.

Current coverage:
  - Missing `work/` is treated as a clean initial runtime state.
  - `work/plans/active/` may contain at most one active plan directory.
  - An active plan package must contain plan.md / tasks.json / handoff.md.
  - `workflow-state.activePlanRef` must match the active plan directory.
  - The active plan's tasks.json must satisfy schema and have at most one active task.
  - Production Python and extensionless scripts under `.harness/scripts/` must not
    write `workflow-state.json` directly.

Exit codes:
  0  lint passed
  1  Harness invariant violation
  2  runtime error (missing schema / JSON parse failure / missing dependency)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: jsonschema>=4.18 is required; run `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


ACTIVE_STATUSES = {"implementing", "testing", "reviewing"}
PLAN_ID_RE = re.compile(r"^[A-Z]+-[0-9]+$")
WORKFLOW_STATE_FILE = "workflow-state.json"
SOURCE_SCAN_ALLOWLIST = {"state-write.py", "lint-harness.py", "session-start.py"}
HANDOFF_REQUIRED_FIELDS = (
    "workflowId",
    "planRef",
    "activeTaskId",
    "currentPhase",
    "taskStatus",
    "ownerRole",
    "sourceSessionId",
)
HANDOFF_REQUIRED_SECTIONS = (
    "## Current Status",
    "## Role Handoff",
    "## Risks",
    "## Next Action",
)
HANDOFF_ROLE_FIELDS = ("fromRole", "toRole", "reason", "stateSource")


class HarnessRuntimeError(Exception):
    pass


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise HarnessRuntimeError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HarnessRuntimeError(f"JSON parse failed {path}: {exc}") from exc


def validate_schema(data: Any, schema_path: Path, label: str) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
        errors.append(f"[schema] {label} {loc}: {err.message}")
    return errors


def active_root(root: Path) -> Path:
    return root / "work" / "plans" / "active"


def list_active_plan_dirs(root: Path, errors: list[str]) -> list[Path]:
    path = active_root(root)
    if not path.exists():
        return []
    if not path.is_dir():
        errors.append(f"[directory] {path} must be a directory")
        return []

    entries = sorted(path.iterdir(), key=lambda item: item.name)
    non_dirs = [item for item in entries if not item.is_dir()]
    for item in non_dirs:
        errors.append(f"[directory] active plan root must not contain non-directory entries: {item}")

    dirs = [item for item in entries if item.is_dir()]
    if len(dirs) > 1:
        names = ", ".join(item.name for item in dirs)
        errors.append(f"[directory] work/plans/active/ allows at most one active plan directory; found: {names}")

    for plan_dir in dirs:
        if not PLAN_ID_RE.match(plan_dir.name):
            errors.append(f"[directory] active plan directory name must match PLAN-001 shape: {plan_dir.name}")

    return dirs


def anchor_exists(plan_text: str, anchor: str) -> bool:
    pattern = rf"""<a\s+id=["']{re.escape(anchor)}["']\s*></a>"""
    return re.search(pattern, plan_text) is not None


def validate_task_manifest_semantics(manifest: Any, plan_dir: Path, plan_text: str | None) -> list[str]:
    if not isinstance(manifest, dict):
        return [f"[tasks] {plan_dir / 'tasks.json'} top-level JSON must be an object"]

    errors: list[str] = []
    if manifest.get("planId") != plan_dir.name:
        errors.append(
            f"[tasks] {plan_dir / 'tasks.json'} planId={manifest.get('planId')!r} "
            f"must equal directory name {plan_dir.name!r}"
        )

    tasks = manifest.get("tasks", [])
    if not isinstance(tasks, list):
        return errors

    ids: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("taskId")
        if task_id in ids:
            errors.append(f"[tasks] {plan_dir / 'tasks.json'} contains duplicate taskId: {task_id}")
        ids.add(task_id)

    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("taskId")
        for dependency in task.get("dependsOn", []):
            if dependency not in ids:
                errors.append(f"[tasks] {task_id}: unknown dependsOn: {dependency}")
        anchor = task.get("planSection")
        if plan_text is not None and isinstance(anchor, str) and not anchor_exists(plan_text, anchor):
            errors.append(f"[tasks] {task_id}: planSection anchor is missing from plan.md: {anchor}")

    active_tasks = [
        task for task in tasks
        if isinstance(task, dict) and task.get("status") in ACTIVE_STATUSES
    ]
    if len(active_tasks) > 1:
        labels = ", ".join(f"{task.get('taskId')}:{task.get('status')}" for task in active_tasks)
        errors.append(f"[tasks] {plan_dir / 'tasks.json'} contains multiple active tasks: {labels}")

    return errors


def lint_active_plan_package(plan_dir: Path, tasks_schema: Path) -> tuple[list[str], dict | None]:
    errors: list[str] = []
    required_files = ("plan.md", "tasks.json", "handoff.md")
    for filename in required_files:
        if not (plan_dir / filename).exists():
            errors.append(f"[directory] active plan {plan_dir.name} is missing {filename}")

    handoff_path = plan_dir / "handoff.md"
    if handoff_path.exists():
        errors += validate_handoff_structure(handoff_path)

    manifest: dict | None = None
    tasks_path = plan_dir / "tasks.json"
    if tasks_path.exists():
        loaded = load_json(tasks_path)
        if isinstance(loaded, dict):
            manifest = loaded
        errors += validate_schema(loaded, tasks_schema, str(tasks_path))
        plan_text = None
        plan_path = plan_dir / "plan.md"
        if plan_path.exists():
            plan_text = plan_path.read_text(encoding="utf-8")
        errors += validate_task_manifest_semantics(loaded, plan_dir, plan_text)

    return errors, manifest


def has_handoff_field(text: str, field: str) -> bool:
    return re.search(rf"(?m)^-\s*{re.escape(field)}\s*:", text) is not None


def handoff_metadata_block(text: str) -> str:
    match = re.search(r"(?m)^##\s+", text)
    return text[:match.start()] if match else text


def validate_handoff_structure(handoff_path: Path) -> list[str]:
    text = handoff_path.read_text(encoding="utf-8")
    errors: list[str] = []

    if not text.startswith("# Handoff"):
        errors.append(f"[handoff] {handoff_path} must start with '# Handoff'")

    metadata = handoff_metadata_block(text)
    missing_fields = [
        field for field in HANDOFF_REQUIRED_FIELDS if not has_handoff_field(metadata, field)
    ]
    if missing_fields:
        errors.append(
            f"[handoff] {handoff_path} is missing required fields: {', '.join(missing_fields)}"
        )

    missing_sections = [section for section in HANDOFF_REQUIRED_SECTIONS if section not in text]
    if missing_sections:
        errors.append(
            f"[handoff] {handoff_path} is missing required sections: {', '.join(missing_sections)}"
        )

    role_section_match = re.search(
        r"(?ms)^## Role Handoff\s*(?P<body>.*?)(?=^## |\Z)",
        text,
    )
    role_body = role_section_match.group("body") if role_section_match else ""
    missing_role_fields = [
        field for field in HANDOFF_ROLE_FIELDS if not has_handoff_field(role_body, field)
    ]
    if missing_role_fields:
        errors.append(
            f"[handoff] {handoff_path} Role Handoff is missing required fields: "
            f"{', '.join(missing_role_fields)}"
        )

    return errors


def lint_workflow_state(
    root: Path,
    workflow_schema: Path,
    active_dirs: list[Path],
    manifest_by_dir: dict[Path, dict | None],
) -> list[str]:
    errors: list[str] = []
    state_path = root / "work" / WORKFLOW_STATE_FILE
    if not state_path.exists():
        if active_dirs:
            names = ", ".join(item.name for item in active_dirs)
            errors.append(f"[state] workflow-state.json is missing while active plan directories exist: {names}")
        return errors

    state = load_json(state_path)
    errors += validate_schema(state, workflow_schema, str(state_path))
    if not isinstance(state, dict):
        return errors

    active_plan_ref = state.get("activePlanRef")
    active_task_id = state.get("activeTaskId")
    if active_plan_ref is None:
        if active_dirs:
            names = ", ".join(item.name for item in active_dirs)
            errors.append(f"[state] activePlanRef is null but work/plans/active/ contains active plans: {names}")
        if active_task_id is not None:
            errors.append("[state] activeTaskId must be null when activePlanRef is null")
        return errors

    if not isinstance(active_plan_ref, str):
        return errors

    plan_path = (state_path.parent / active_plan_ref).resolve()
    if plan_path.name != "plan.md":
        errors.append(f"[state] activePlanRef must point to plan.md: {active_plan_ref}")
    if not plan_path.exists():
        errors.append(f"[state] activePlanRef points to a missing plan.md: {plan_path}")

    expected_dir = plan_path.parent
    if not active_dirs:
        errors.append(f"[state] activePlanRef points to {expected_dir.name}, but work/plans/active/ is empty")
        return errors

    if len(active_dirs) == 1 and active_dirs[0].resolve() != expected_dir:
        errors.append(
            f"[state] activePlanRef points to {expected_dir.name}, "
            f"but the only active plan directory is {active_dirs[0].name}"
        )

    manifest = manifest_by_dir.get(expected_dir)
    if manifest and active_task_id is not None:
        ids = {
            task.get("taskId")
            for task in manifest.get("tasks", [])
            if isinstance(task, dict)
        }
        if active_task_id not in ids:
            errors.append(f"[state] activeTaskId={active_task_id!r} is not in active plan tasks.json")

    return errors


def node_contains_workflow_state(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if child.value == WORKFLOW_STATE_FILE or child.value.endswith("/" + WORKFLOW_STATE_FILE):
                return True
    return False


def write_mode_arg(call: ast.Call) -> bool:
    mode_node: ast.AST | None = None
    if len(call.args) >= 2:
        mode_node = call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode_node = keyword.value
            break
    if mode_node is None:
        return False
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return any(ch in mode_node.value for ch in ("w", "a", "x", "+"))
    return False


class WorkflowStateWriteVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.state_path_vars: set[str] = set()
        self.findings: list[int] = []

    def expr_refers_to_state_path(self, node: ast.AST) -> bool:
        if node_contains_workflow_state(node):
            return True
        return isinstance(node, ast.Name) and node.id in self.state_path_vars

    def visit_Assign(self, node: ast.Assign) -> None:
        if node_contains_workflow_state(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.state_path_vars.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and node_contains_workflow_state(node.value):
            if isinstance(node.target, ast.Name):
                self.state_path_vars.add(node.target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func

        if isinstance(func, ast.Attribute):
            if func.attr in {"write_text", "write_bytes"} and self.expr_refers_to_state_path(func.value):
                self.findings.append(node.lineno)
            if func.attr == "open" and self.expr_refers_to_state_path(func.value) and write_mode_arg(node):
                self.findings.append(node.lineno)
            if func.attr in {"replace", "rename"}:
                if any(self.expr_refers_to_state_path(arg) for arg in node.args):
                    self.findings.append(node.lineno)

        if isinstance(func, ast.Name) and func.id == "open":
            if node.args and self.expr_refers_to_state_path(node.args[0]) and write_mode_arg(node):
                self.findings.append(node.lineno)

        self.generic_visit(node)


def scan_for_direct_state_writes(root: Path) -> list[str]:
    scripts_dir = root / ".harness" / "scripts"
    if not scripts_dir.exists():
        return []

    errors: list[str] = []
    candidates = [
        item for item in scripts_dir.iterdir()
        if item.is_file() and item.name != "__init__.py" and item.suffix in {"", ".py"}
    ]
    for script in sorted(candidates, key=lambda item: item.name):
        if script.name in SOURCE_SCAN_ALLOWLIST or script.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
        except SyntaxError as exc:
            errors.append(f"[source] {script}: Python syntax error; cannot inspect direct state writes: {exc}")
            continue

        visitor = WorkflowStateWriteVisitor()
        visitor.visit(tree)
        for line in sorted(set(visitor.findings)):
            errors.append(f"[source] direct workflow-state.json writes are forbidden: {script}:{line}; use state-write.py")

    return errors


def run(root: Path, workflow_schema: Path, tasks_schema: Path) -> int:
    errors: list[str] = []
    runtime_errors: list[str] = []

    try:
        active_dirs = list_active_plan_dirs(root, errors)
        manifest_by_dir: dict[Path, dict | None] = {}
        for plan_dir in active_dirs:
            plan_errors, manifest = lint_active_plan_package(plan_dir, tasks_schema)
            errors += plan_errors
            manifest_by_dir[plan_dir.resolve()] = manifest

        errors += lint_workflow_state(root, workflow_schema, active_dirs, manifest_by_dir)
        errors += scan_for_direct_state_writes(root)
    except HarnessRuntimeError as exc:
        runtime_errors.append(str(exc))
    except OSError as exc:
        runtime_errors.append(str(exc))

    if runtime_errors:
        print(f"✗ Harness lint runtime failed ({len(runtime_errors)} issue(s)):")
        for error in runtime_errors:
            print(f"  - {error}")
        return 2

    if errors:
        print(f"✗ Harness lint validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"✓ Harness lint validation passed: {root}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Lint Harness directory-level invariants")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument("--workflow-schema", type=Path, help="workflow-state.schema.json path")
    parser.add_argument("--tasks-schema", type=Path, help="tasks.schema.json path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = args.root.resolve()
    workflow_schema = args.workflow_schema or (root / ".harness" / "schemas" / "workflow-state.schema.json")
    tasks_schema = args.tasks_schema or (root / ".harness" / "schemas" / "tasks.schema.json")
    return run(root, workflow_schema, tasks_schema)


if __name__ == "__main__":
    sys.exit(main())
