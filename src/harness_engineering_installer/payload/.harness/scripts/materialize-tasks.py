#!/usr/bin/env python3
"""
materialize-tasks.py

从已通过 Plan Review Gate 的 Harness plan.md 任务契约区块生成 tasks.json。

边界：
  - 只接受包含 `## Plan Review Gate` 且 `Status: passed` 的 plan.md。
  - 只解析结构化任务契约，不从自由文本猜任务。
  - 只生成 idle tasks，并初始化 verification/review gate，不激活 task，不写 workflow-state.json。
  - 写入前校验 tasks.schema.json，并检查 taskId / anchor / dependsOn。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Iterable

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: 需要 jsonschema>=4.18，请执行 `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


ANCHOR_RE = re.compile(r"""<a\s+id=["'](?P<id>[a-z0-9][a-z0-9-]*)["']\s*></a>""")
TASK_HEADING_RE = re.compile(r"^###\s+(?P<task_id>[A-Z]+-[0-9]+(?:\.[0-9]+)*):\s+(?P<title>.+?)\s*$")
SECTION_RE = re.compile(r"^(?P<name>Goal|Files|Depends on|Acceptance|Verification):(?P<tail>.*)$")
FILE_RE = re.compile(r"^-\s*(?P<kind>Create|Modify|Test):\s*(?P<value>.+?)\s*$", re.IGNORECASE)
RUN_RE = re.compile(r"^-\s*Run:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
CHECK_RE = re.compile(r"^-\s*Check:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
PLAN_REVIEW_HEADING_RE = re.compile(r"(?m)^##\s+Plan Review Gate\s*$")
H2_HEADING_RE = re.compile(r"(?m)^##\s+")
PLAN_REVIEW_PASSED_RE = re.compile(r"(?mi)^Status:\s*passed\s*$")


class MaterializeError(Exception):
    pass


def default_review() -> dict:
    return {
        "score": 0,
        "threshold": 85,
        "lastResult": "not_run",
        "rubricVersion": "review-rubric-v1",
        "checks": [],
        "findings": [],
        "reportRef": "",
    }


def strip_ticks(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == "`" and value[-1] == "`":
        return value[1:-1].strip()
    return value


def bullet_value(line: str) -> str:
    stripped = line.strip()
    if not stripped.startswith("-"):
        raise MaterializeError(f"expected bullet line, got: {line!r}")
    return stripped[1:].strip()


def parse_depends(value: str) -> list[str]:
    value = value.strip()
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",") if item.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


def section_name(line: str) -> str | None:
    match = SECTION_RE.match(line.strip())
    return match.group("name").lower() if match else None


def collect_section(lines: list[str], start: int) -> tuple[list[str], int]:
    out: list[str] = []
    i = start
    while i < len(lines):
        stripped = lines[i].strip()
        if TASK_HEADING_RE.match(stripped) or ANCHOR_RE.search(stripped):
            break
        if section_name(stripped) is not None:
            break
        if stripped:
            out.append(stripped)
        i += 1
    return out, i


def parse_task_body(task_id: str, lines: list[str]) -> dict:
    files = {"create": [], "modify": [], "test": []}
    depends_on: list[str] | None = None
    acceptance: list[str] = []
    commands: list[str] = []
    checks: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        match = SECTION_RE.match(line)
        if not match:
            i += 1
            continue

        name = match.group("name").lower()
        tail = match.group("tail").strip()
        i += 1

        if name == "goal":
            continue

        if name == "depends on":
            depends_on = parse_depends(tail)
            continue

        section_lines, i = collect_section(lines, i)

        if name == "files":
            for item in section_lines:
                file_match = FILE_RE.match(item)
                if not file_match:
                    raise MaterializeError(f"{task_id}: invalid Files line: {item!r}")
                kind = file_match.group("kind").lower()
                files[kind].append(strip_ticks(file_match.group("value")))
            continue

        if name == "acceptance":
            acceptance.extend(bullet_value(item) for item in section_lines)
            continue

        if name == "verification":
            for item in section_lines:
                run_match = RUN_RE.match(item)
                if run_match:
                    commands.append(strip_ticks(run_match.group("value")))
                    continue
                check_match = CHECK_RE.match(item)
                if check_match:
                    checks.append(strip_ticks(check_match.group("value")))
                    continue
                checks.append(bullet_value(item))
            continue

    if depends_on is None:
        raise MaterializeError(f"{task_id}: missing Depends on section")
    if not any(files.values()):
        raise MaterializeError(f"{task_id}: missing file boundary")
    if not acceptance:
        raise MaterializeError(f"{task_id}: missing acceptance")
    if not commands and not checks:
        raise MaterializeError(f"{task_id}: missing verification")

    return {
        "dependsOn": depends_on,
        "files": files,
        "acceptance": acceptance,
        "verification": {
            "commands": commands,
            "checks": checks,
            "lastResult": "not_run",
        },
    }


def plan_review_gate_section(plan_text: str) -> str:
    match = PLAN_REVIEW_HEADING_RE.search(plan_text)
    if not match:
        raise MaterializeError("Plan Review Gate is required before tasks.json materialization")

    start = match.end()
    next_heading = H2_HEADING_RE.search(plan_text, start)
    end = next_heading.start() if next_heading else len(plan_text)
    return plan_text[start:end]


def ensure_plan_review_gate_passed(plan_text: str) -> None:
    section = plan_review_gate_section(plan_text)
    if not PLAN_REVIEW_PASSED_RE.search(section):
        raise MaterializeError(
            "Plan Review Gate must contain `Status: passed` before tasks.json materialization"
        )


def extract_tasks(plan_text: str) -> list[dict]:
    lines = plan_text.splitlines()
    tasks: list[dict] = []
    pending_anchor: str | None = None
    pending_anchor_line: int | None = None
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        anchor_match = ANCHOR_RE.search(stripped)
        if anchor_match:
            pending_anchor = anchor_match.group("id")
            pending_anchor_line = i + 1
            i += 1
            continue

        heading_match = TASK_HEADING_RE.match(stripped)
        if not heading_match:
            i += 1
            continue

        task_id = heading_match.group("task_id")
        title = heading_match.group("title").strip()
        if pending_anchor is None:
            raise MaterializeError(f"{task_id}: missing stable anchor before task heading")

        start = i + 1
        i = start
        while i < len(lines):
            next_line = lines[i].strip()
            if ANCHOR_RE.search(next_line) or TASK_HEADING_RE.match(next_line):
                break
            i += 1

        body = parse_task_body(task_id, lines[start:i])
        tasks.append(
            {
                "taskId": task_id,
                "title": title,
                "planSection": pending_anchor,
                "status": "idle",
                "currentStep": "",
                "nextAction": "",
                "ownerRole": "developer",
                **body,
                "review": default_review(),
                "blockedReason": "",
            }
        )
        pending_anchor = None
        pending_anchor_line = None

    if pending_anchor is not None:
        raise MaterializeError(f"anchor {pending_anchor!r} on line {pending_anchor_line} has no task heading")
    if not tasks:
        raise MaterializeError("no structured task contracts found")
    return tasks


def validate_manifest(manifest: dict, schema: dict, plan_text: str) -> None:
    task_ids: set[str] = set()
    anchors: set[str] = set()

    for task in manifest["tasks"]:
        task_id = task["taskId"]
        anchor = task["planSection"]
        if task_id in task_ids:
            raise MaterializeError(f"duplicate taskId: {task_id}")
        if anchor in anchors:
            raise MaterializeError(f"duplicate planSection anchor: {anchor}")
        task_ids.add(task_id)
        anchors.add(anchor)

    for task in manifest["tasks"]:
        for dependency in task["dependsOn"]:
            if dependency not in task_ids:
                raise MaterializeError(f"{task['taskId']}: unknown dependsOn: {dependency}")
        anchor = task["planSection"]
        if not re.search(rf"""<a\s+id=["']{re.escape(anchor)}["']\s*></a>""", plan_text):
            raise MaterializeError(f"{task['taskId']}: missing anchor in plan.md: {anchor}")

    validate_dependency_graph_is_acyclic(manifest["tasks"])

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda err: list(err.absolute_path))
    if errors:
        lines = []
        for err in errors:
            loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
            lines.append(f"{loc}: {err.message}")
        raise MaterializeError("schema validation failed:\n" + "\n".join(lines))


def validate_dependency_graph_is_acyclic(tasks: list[dict]) -> None:
    graph = {task["taskId"]: list(task["dependsOn"]) for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            start = stack.index(task_id)
            cycle = [*stack[start:], task_id]
            raise MaterializeError(f"cyclic dependsOn: {' -> '.join(cycle)}")

        visiting.add(task_id)
        stack.append(task_id)
        for dependency in graph[task_id]:
            visit(dependency)
        stack.pop()
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in graph:
        visit(task_id)


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "tasks.schema.json"


def build_manifest(plan_path: Path, out_path: Path, schema_path: Path, plan_id: str | None) -> dict:
    plan_text = plan_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    ensure_plan_review_gate_passed(plan_text)
    resolved_plan_id = plan_id or plan_path.parent.name
    schema_ref = os.path.relpath(schema_path.resolve(), out_path.parent.resolve())
    manifest = {
        "$schema": schema_ref,
        "planId": resolved_plan_id,
        "planRef": "./plan.md",
        "tasks": extract_tasks(plan_text),
    }
    validate_manifest(manifest, schema, plan_text)
    return manifest


def run(args: argparse.Namespace) -> int:
    plan_path: Path = args.plan
    out_path: Path = args.out or (plan_path.parent / "tasks.json")
    schema_path: Path = args.schema

    if not plan_path.exists():
        print(f"ERROR: plan.md not found: {plan_path}", file=sys.stderr)
        return 2
    if plan_path.name != "plan.md":
        print(f"ERROR: input must be a plan.md file: {plan_path}", file=sys.stderr)
        return 1
    if not schema_path.exists():
        print(f"ERROR: schema not found: {schema_path}", file=sys.stderr)
        return 2

    try:
        manifest = build_manifest(plan_path, out_path, schema_path, args.plan_id)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except MaterializeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        atomic_write_json(out_path, manifest)
    except OSError as exc:
        print(f"ERROR: failed to write {out_path}: {exc}", file=sys.stderr)
        return 2

    print(f"✓ wrote {out_path} ({len(manifest['tasks'])} tasks)")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize Harness plan.md task contracts into tasks.json")
    parser.add_argument("plan", type=Path, help="Path to work/plans/active/<PLAN-ID>/plan.md")
    parser.add_argument("--out", type=Path, help="Output tasks.json path; defaults to plan.md sibling")
    parser.add_argument("--schema", type=Path, default=default_schema_path(), help="tasks.schema.json path")
    parser.add_argument("--plan-id", help="Override planId; defaults to plan.md parent directory name")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
