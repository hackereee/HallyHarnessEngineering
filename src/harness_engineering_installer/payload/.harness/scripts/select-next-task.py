#!/usr/bin/env python3
"""
select-next-task.py

Select the next executable task from a plan directory's tasks.json.

Responsibilities:
  - Read only tasks.json; do not write tasks.json or workflow-state.json.
  - Validate tasks.schema.json and check taskId / dependsOn references.
  - When there is no active task, select the first idle task whose dependencies
    are all done.
  - Emit structured suggestions for update-task.py and state-write.py.

Exit codes:
  0  emitted a task activation suggestion, or an archive suggestion when all tasks are done
  1  current task state does not allow selection, or no executable idle task exists
  2  runtime error (missing file / JSON parse failure / missing dependency)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: jsonschema>=4.18 is required; run `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


ACTIVE_STATUSES = {"implementing", "testing", "reviewing"}


class SelectNextTaskError(Exception):
    pass


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "tasks.schema.json"


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise SelectNextTaskError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SelectNextTaskError(f"JSON parse failed {path}: {exc}") from exc


def validate_manifest(manifest: dict, schema: dict) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda err: list(err.absolute_path))
    if errors:
        lines = []
        for err in errors:
            loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
            lines.append(f"{loc}: {err.message}")
        raise SelectNextTaskError("schema validation failed:\n" + "\n".join(lines))

    tasks = manifest.get("tasks", [])
    ids: set[str] = set()
    for task in tasks:
        task_id = task.get("taskId")
        if task_id in ids:
            raise SelectNextTaskError(f"duplicate taskId: {task_id}")
        ids.add(task_id)

    for task in tasks:
        for dependency in task.get("dependsOn", []):
            if dependency not in ids:
                raise SelectNextTaskError(f"{task.get('taskId')}: unknown dependsOn: {dependency}")


def task_by_id(manifest: dict) -> dict[str, dict]:
    return {task["taskId"]: task for task in manifest.get("tasks", [])}


def dependencies_done(task: dict, tasks_by_id: dict[str, dict]) -> bool:
    return all(tasks_by_id[dependency]["status"] == "done" for dependency in task.get("dependsOn", []))


def generated_next_action(task: dict) -> str:
    existing = task.get("nextAction", "").strip()
    if existing:
        return existing
    return f"Execute {task['taskId']}"


def state_patch_for_task(task: dict, next_action: str) -> list[dict]:
    return [
        {"op": "replace", "path": "/currentPhase", "value": "implementing"},
        {"op": "replace", "path": "/ownerRole", "value": "developer"},
        {"op": "replace", "path": "/activeTaskId", "value": task["taskId"]},
        {"op": "replace", "path": "/nextAction", "value": next_action},
    ]


def archive_state_patch() -> list[dict]:
    return [
        {"op": "replace", "path": "/currentPhase", "value": "archiving"},
        {"op": "replace", "path": "/ownerRole", "value": "developer"},
        {"op": "replace", "path": "/activeTaskId", "value": None},
        {"op": "replace", "path": "/nextAction", "value": "Archive current plan package"},
    ]


def build_selection(manifest: dict) -> dict:
    tasks = manifest.get("tasks", [])
    active_tasks = [task for task in tasks if task.get("status") in ACTIVE_STATUSES]
    if active_tasks:
        labels = ", ".join(f"{task['taskId']}:{task['status']}" for task in active_tasks)
        raise SelectNextTaskError(f"active task already exists: {labels}")

    if all(task.get("status") == "done" for task in tasks):
        return {
            "kind": "archive",
            "planId": manifest["planId"],
            "task": None,
            "taskUpdate": None,
            "statePatch": archive_state_patch(),
        }

    tasks_by_id = task_by_id(manifest)
    for task in tasks:
        if task.get("status") != "idle":
            continue
        if not dependencies_done(task, tasks_by_id):
            continue
        next_action = generated_next_action(task)
        return {
            "kind": "task",
            "planId": manifest["planId"],
            "task": task,
            "taskUpdate": {
                "taskId": task["taskId"],
                "status": "implementing",
                "ownerRole": "developer",
                "nextAction": next_action,
            },
            "statePatch": state_patch_for_task(task, next_action),
        }

    raise SelectNextTaskError("no executable idle task")


def run(args: argparse.Namespace) -> int:
    if not args.tasks.exists():
        print(f"ERROR: tasks.json not found: {args.tasks}", file=sys.stderr)
        return 2
    if not args.schema.exists():
        print(f"ERROR: schema not found: {args.schema}", file=sys.stderr)
        return 2

    try:
        manifest = load_json(args.tasks)
        schema = load_json(args.schema)
        if not isinstance(manifest, dict):
            raise SelectNextTaskError(f"{args.tasks} top-level JSON must be an object")
        validate_manifest(manifest, schema)
        selection = build_selection(manifest)
    except SelectNextTaskError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(selection, ensure_ascii=False, indent=2))
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select next executable Harness task from tasks.json")
    parser.add_argument("--tasks", type=Path, required=True, help="Path to work/plans/active/<PLAN-ID>/tasks.json")
    parser.add_argument("--schema", type=Path, default=default_schema_path(), help="tasks.schema.json path")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
