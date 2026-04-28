#!/usr/bin/env python3
"""
backlog-consume.py

Remove a pending backlog item only after a downstream workflow or active plan
has taken ownership of it. The script writes only work/backlog/backlogs.json
and work/backlog/consumed.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, ValidationError
from jsonschema.validators import extend


class BacklogConsumeError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def unique_item_properties(validator, properties, instance, schema):
    if not isinstance(instance, list):
        return
    for property_name in properties:
        seen: dict[object, int] = {}
        for index, item in enumerate(instance):
            if not isinstance(item, dict) or property_name not in item:
                continue
            value = item[property_name]
            if value in seen:
                yield ValidationError(
                    f"{property_name!r} must be unique; {value!r} appears at indexes "
                    f"{seen[value]} and {index}"
                )
            seen[value] = index


BacklogsValidator = extend(
    Draft202012Validator,
    validators={"x-harness-uniqueItemProperties": unique_item_properties},
)


TARGET_RE = re.compile(r"^(?P<kind>plan|workflow):(?P<value>.+)$")
PLAN_ID_RE = re.compile(r"^[A-Z]+-[0-9]+$")
WORKFLOW_ID_RE = re.compile(r"^workflow-[a-z0-9][a-z0-9-]*$")
PLAN_REVIEW_HEADING_RE = re.compile(r"(?m)^##\s+Plan Review Gate\s*$")
PLAN_REVIEW_PASSED_RE = re.compile(r"(?mi)^Status:\s*passed\s*$")
H2_HEADING_RE = re.compile(r"(?m)^##\s+")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BacklogConsumeError(f"文件不存在: {path}", 2) from exc
    except json.JSONDecodeError as exc:
        raise BacklogConsumeError(f"JSON 解析失败 {path}: {exc}", 1) from exc


def validation_errors(validator: Draft202012Validator, data: dict) -> list[str]:
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.absolute_path))
    return [f"{'/'.join(str(part) for part in err.absolute_path) or '<root>'}: {err.message}" for err in errors]


def validate_with_schema(schema: dict, data: dict, *, label: str, backlog_store: bool = False) -> None:
    Draft202012Validator.check_schema(schema)
    validator: Draft202012Validator
    validator = BacklogsValidator(schema) if backlog_store else Draft202012Validator(schema)
    errors = validation_errors(validator, data)
    if errors:
        joined = "\n".join(f"  - {error}" for error in errors)
        raise BacklogConsumeError(f"{label} 校验失败:\n{joined}", 1)


def store_path(root: Path) -> Path:
    return root / "work" / "backlog" / "backlogs.json"


def consumed_path(root: Path) -> Path:
    return root / "work" / "backlog" / "consumed.jsonl"


def backlogs_schema_path(root: Path) -> Path:
    return root / ".harness" / "schemas" / "backlogs.schema.json"


def event_schema_path(root: Path) -> Path:
    return root / ".harness" / "schemas" / "backlog-consumption-event.schema.json"


def tasks_schema_path(root: Path) -> Path:
    return root / ".harness" / "schemas" / "tasks.schema.json"


def workflow_schema_path(root: Path) -> Path:
    return root / ".harness" / "schemas" / "workflow-state.schema.json"


def validate_state_script(root: Path) -> Path:
    return root / ".harness" / "scripts" / "validate-state.py"


def parse_consumed_at(raw: str | None) -> str:
    if raw is None:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BacklogConsumeError(f"--consumed-at 不是合法 ISO 8601 时间: {raw}", 2) from exc
    if parsed.tzinfo is None:
        raise BacklogConsumeError("--consumed-at 必须包含时区，例如 2026-04-28T12:30:00+08:00", 2)
    return raw


def parse_target_ref(raw: str) -> tuple[str, str]:
    match = TARGET_RE.fullmatch(raw)
    if not match:
        raise BacklogConsumeError("targetRef 必须是 plan:<PLAN-ID> 或 workflow:<workflowId>", 1)
    kind = match.group("kind")
    value = match.group("value")
    if kind == "plan" and not PLAN_ID_RE.fullmatch(value):
        raise BacklogConsumeError(f"targetRef plan id 非法: {raw}", 1)
    if kind == "workflow" and not WORKFLOW_ID_RE.fullmatch(value):
        raise BacklogConsumeError(f"targetRef workflow id 非法: {raw}", 1)
    return kind, value


def load_and_validate_store(root: Path) -> dict:
    store = load_json(store_path(root))
    if not isinstance(store, dict):
        raise BacklogConsumeError("backlogs.json 根节点必须是对象", 1)
    schema = load_json(backlogs_schema_path(root))
    validate_with_schema(schema, store, label="backlogs.json", backlog_store=True)
    return store


def find_item(store: dict, item_id: str) -> dict:
    for item in store.get("items", []):
        if isinstance(item, dict) and item.get("id") == item_id:
            return item
    raise BacklogConsumeError(f"unknown backlog id: {item_id}", 1)


def plan_review_gate_section(plan_text: str) -> str:
    match = PLAN_REVIEW_HEADING_RE.search(plan_text)
    if not match:
        raise BacklogConsumeError("plan target missing Plan Review Gate", 1)
    start = match.end()
    next_heading = H2_HEADING_RE.search(plan_text, start)
    end = next_heading.start() if next_heading else len(plan_text)
    return plan_text[start:end]


def ensure_plan_review_passed(plan_text: str) -> None:
    section = plan_review_gate_section(plan_text)
    if not PLAN_REVIEW_PASSED_RE.search(section):
        raise BacklogConsumeError("plan target Plan Review Gate is not passed", 1)


def validate_plan_target(root: Path, plan_id: str, item: dict) -> None:
    plan_dir = root / "work" / "plans" / "active" / plan_id
    plan_path = plan_dir / "plan.md"
    tasks_path = plan_dir / "tasks.json"
    handoff_path = plan_dir / "handoff.md"
    for path in (plan_path, tasks_path, handoff_path):
        if not path.exists():
            raise BacklogConsumeError(f"plan target missing required file: {path}", 1)

    plan_text = plan_path.read_text(encoding="utf-8")
    handoff_text = handoff_path.read_text(encoding="utf-8")
    ensure_plan_review_passed(plan_text)

    tasks = load_json(tasks_path)
    if not isinstance(tasks, dict):
        raise BacklogConsumeError("tasks.json 根节点必须是对象", 1)
    validate_with_schema(load_json(tasks_schema_path(root)), tasks, label="tasks.json")

    source_tokens = [item["id"], item["sourceRef"]]
    downstream_text = plan_text + "\n" + handoff_text
    if not any(token in downstream_text for token in source_tokens):
        raise BacklogConsumeError("plan target does not reference backlog source", 1)


def run_state_validator(root: Path) -> None:
    command = [
        sys.executable,
        str(validate_state_script(root)),
        "--state",
        str(root / "work" / "workflow-state.json"),
        "--schema",
        str(workflow_schema_path(root)),
    ]
    proc = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if proc.returncode != 0:
        output = (proc.stdout or "") + (proc.stderr or "")
        raise BacklogConsumeError(f"workflow state validation failed:\n{output.strip()}", 1)


def session_audit_references_source(root: Path, item: dict) -> bool:
    sessions_dir = root / "work" / "sessions"
    if not sessions_dir.exists():
        return False
    for path in sessions_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if item["id"] in text or item["sourceRef"] in text:
            return True
    return False


def validate_workflow_target(root: Path, workflow_id: str, item: dict) -> None:
    run_state_validator(root)
    state = load_json(root / "work" / "workflow-state.json")
    if state.get("workflowId") != workflow_id:
        raise BacklogConsumeError(f"workflow target does not match workflow-state.json: {workflow_id}", 1)
    if state.get("activePlanRef") is not None or state.get("activeTaskId") is not None:
        raise BacklogConsumeError("workflow target must be a direct workflow with null active refs", 1)
    if not session_audit_references_source(root, item):
        raise BacklogConsumeError("workflow target missing session audit source reference", 1)


def build_event(args: argparse.Namespace, item: dict) -> dict:
    return {
        "eventType": "backlog.consumed",
        "backlogId": item["id"],
        "consumedAt": parse_consumed_at(args.consumed_at),
        "targetRef": args.target_ref,
        "reason": args.reason,
        "item": item,
    }


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def append_jsonl(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def restore_consumed_log(path: Path, previous_text: str | None) -> None:
    if previous_text is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    atomic_write_text(path, previous_text)


def consume(root: Path, args: argparse.Namespace) -> dict:
    kind, target_id = parse_target_ref(args.target_ref)
    store = load_and_validate_store(root)
    item = find_item(store, args.id)

    if kind == "plan":
        validate_plan_target(root, target_id, item)
    else:
        validate_workflow_target(root, target_id, item)

    event = build_event(args, item)
    validate_with_schema(load_json(event_schema_path(root)), event, label="backlog consumption event")

    next_store = {
        **store,
        "items": [existing for existing in store["items"] if existing.get("id") != args.id],
    }
    validate_with_schema(load_json(backlogs_schema_path(root)), next_store, label="backlogs.json", backlog_store=True)

    event_path = consumed_path(root)
    previous_events = event_path.read_text(encoding="utf-8") if event_path.exists() else None
    append_jsonl(event_path, event)
    try:
        atomic_write_json(store_path(root), next_store)
    except OSError as exc:
        try:
            restore_consumed_log(event_path, previous_events)
        except OSError as rollback_exc:
            raise BacklogConsumeError(
                "failed to update backlogs.json after writing consumed event, "
                f"and rollback failed: {rollback_exc}",
                2,
            ) from exc
        raise BacklogConsumeError(
            f"failed to update backlogs.json after writing consumed event; event rolled back: {exc}",
            2,
        ) from exc
    return {"status": "consumed", "event": event}


def run(args: argparse.Namespace) -> int:
    result = consume(args.root.resolve(), args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Consume a pending Harness backlog item")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument("--id", required=True, help="Backlog item ID, e.g. BL-001")
    parser.add_argument("--target-ref", required=True, dest="target_ref", help="plan:<PLAN-ID> or workflow:<workflowId>")
    parser.add_argument("--reason", required=True, help="Reason for consumption")
    parser.add_argument("--consumed-at", help="ISO 8601 timestamp with timezone")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        return run(args)
    except BacklogConsumeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
