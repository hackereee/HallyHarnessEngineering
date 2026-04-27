#!/usr/bin/env python3
"""
backlog-intake.py

Append incoming work to work/backlog/backlogs.json through a deterministic
gateway. This script does not mutate workflow-state.json, tasks.json, or active
plan files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, ValidationError
from jsonschema.validators import extend


class BacklogIntakeError(Exception):
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


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BacklogIntakeError(f"文件不存在: {path}", 2) from exc
    except json.JSONDecodeError as exc:
        raise BacklogIntakeError(f"JSON 解析失败 {path}: {exc}", 1) from exc


def runtime_schema_ref() -> str:
    return "../../.harness/schemas/backlogs.schema.json"


def store_path(root: Path) -> Path:
    return root / "work" / "backlog" / "backlogs.json"


def schema_path(root: Path) -> Path:
    return root / ".harness" / "schemas" / "backlogs.schema.json"


def template_path(root: Path) -> Path:
    return root / ".harness" / "templates" / "backlogs.template.json"


def validator_for(schema: dict) -> BacklogsValidator:
    Draft202012Validator.check_schema(schema)
    return BacklogsValidator(schema)


def validation_errors(validator: BacklogsValidator, data: dict) -> list[str]:
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.absolute_path))
    return [f"{'/'.join(str(part) for part in err.absolute_path) or '<root>'}: {err.message}" for err in errors]


def validate_store(validator: BacklogsValidator, data: dict, *, label: str) -> None:
    errors = validation_errors(validator, data)
    if errors:
        joined = "\n".join(f"  - {error}" for error in errors)
        raise BacklogIntakeError(f"{label} 校验失败:\n{joined}", 1)


def load_or_initialize_store(root: Path) -> dict:
    path = store_path(root)
    if path.exists():
        data = load_json(path)
    else:
        data = load_json(template_path(root))
    if not isinstance(data, dict):
        raise BacklogIntakeError("backlogs.json 根节点必须是对象", 1)
    data = dict(data)
    data["$schema"] = runtime_schema_ref()
    return data


def next_backlog_id(items: list[dict]) -> str:
    max_seen = 0
    for item in items:
        raw = item.get("id") if isinstance(item, dict) else None
        if not isinstance(raw, str):
            continue
        match = re.fullmatch(r"BL-([0-9]{3})", raw)
        if match:
            max_seen = max(max_seen, int(match.group(1)))
    next_number = max_seen + 1
    if next_number > 999:
        raise BacklogIntakeError("backlog id 已超过 BL-999，需先归档或扩展 schema", 1)
    return f"BL-{next_number:03d}"


def parse_created_at(raw: str | None) -> str:
    if raw is None:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BacklogIntakeError(f"--created-at 不是合法 ISO 8601 时间: {raw}", 2) from exc
    if parsed.tzinfo is None:
        raise BacklogIntakeError("--created-at 必须包含时区，例如 2026-04-27T10:00:00+08:00", 2)
    return raw


def build_item(args: argparse.Namespace, item_id: str) -> dict:
    item = {
        "id": item_id,
        "title": args.title,
        "summary": args.summary,
        "dispatch": args.dispatch,
        "sourceRef": args.source_ref,
        "createdAt": parse_created_at(args.created_at),
    }
    if args.notes:
        item["notes"] = args.notes
    return item


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


def append_backlog_item(root: Path, args: argparse.Namespace) -> dict:
    schema = load_json(schema_path(root))
    validator = validator_for(schema)
    store = load_or_initialize_store(root)
    validate_store(validator, store, label="backlogs.json")

    items = store.get("items")
    if not isinstance(items, list):
        raise BacklogIntakeError("backlogs.json 校验失败:\n  - items: must be array", 1)
    item = build_item(args, next_backlog_id(items))
    next_store = {**store, "items": [*items, item]}
    validate_store(validator, next_store, label="backlogs.json")
    atomic_write_json(store_path(root), next_store)
    return item


def run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    item = append_backlog_item(root, args)
    print(json.dumps({"status": "appended", "item": item}, ensure_ascii=False, indent=2))
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Append an item to the Harness backlog store")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument("--title", required=True, help="Backlog item title")
    parser.add_argument("--summary", required=True, help="Backlog item summary")
    parser.add_argument("--dispatch", choices=("queue", "preempt"), default="queue")
    parser.add_argument("--source-ref", required=True, dest="source_ref", help="Auditable source reference")
    parser.add_argument("--notes", help="Optional intake notes")
    parser.add_argument("--created-at", help="ISO 8601 timestamp with timezone")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        return run(args)
    except BacklogIntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
