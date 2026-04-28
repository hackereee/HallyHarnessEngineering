#!/usr/bin/env python3
"""
update-task.py

`tasks.json` 的 task 状态写入网关。只更新 plan 目录内的 tasks.json，
不写 workflow-state.json。

职责：
  - 定位单个 taskId。
  - 更新 status / ownerRole / currentStep / nextAction / verification / review / blockedReason。
  - 对 active 状态自动补齐 ownerRole：implementing=developer、testing=tester、reviewing=reviewer。
  - 写入前校验 tasks.schema.json。
  - 校验 done 前置条件：verification passed、review passed，且 dependsOn 均为 done。
  - 临时文件 + os.replace 原子落盘。

退出码：
  0  写入成功
  1  更新意图无效或校验失败（tasks.json 未改动）
  2  运行错误（文件缺失 / JSON 解析失败 / 依赖缺失）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: 需要 jsonschema>=4.18，请执行 `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


ACTIVE_ROLE_BY_STATUS = {
    "idle": "developer",
    "implementing": "developer",
    "testing": "tester",
    "reviewing": "reviewer",
}

STATUS_CHOICES = ("idle", "implementing", "testing", "reviewing", "blocked", "done")
OWNER_ROLE_CHOICES = ("developer", "planner", "reviewer", "tester")
VERIFICATION_RESULT_CHOICES = ("not_run", "passed", "failed")
REVIEW_RESULT_CHOICES = ("not_run", "passed", "failed")


class UpdateTaskError(Exception):
    pass


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise UpdateTaskError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise UpdateTaskError(f"JSON parse failed {path}: {exc}") from exc


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


def find_task(manifest: dict, task_id: str) -> dict:
    for task in manifest.get("tasks", []):
        if isinstance(task, dict) and task.get("taskId") == task_id:
            return task
    raise UpdateTaskError(f"unknown taskId: {task_id}")


def append_unique(values: list[str], additions: list[str]) -> None:
    for item in additions:
        if item not in values:
            values.append(item)


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


def parse_review_finding(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UpdateTaskError(f"--review-finding-json must be a JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise UpdateTaskError("--review-finding-json must be a JSON object")
    return value


def apply_updates(task: dict, args: argparse.Namespace) -> None:
    if args.status is not None:
        task["status"] = args.status
        if args.owner_role is None and args.status in ACTIVE_ROLE_BY_STATUS:
            task["ownerRole"] = ACTIVE_ROLE_BY_STATUS[args.status]

    if args.owner_role is not None:
        task["ownerRole"] = args.owner_role
    if args.current_step is not None:
        task["currentStep"] = args.current_step
    if args.next_action is not None:
        task["nextAction"] = args.next_action
    if args.blocked_reason is not None:
        task["blockedReason"] = args.blocked_reason

    verification = task.setdefault(
        "verification",
        {"commands": [], "checks": [], "lastResult": "not_run"},
    )
    if args.verification_last_result is not None:
        verification["lastResult"] = args.verification_last_result
    if args.verification_command:
        append_unique(verification.setdefault("commands", []), args.verification_command)
    if args.verification_check:
        append_unique(verification.setdefault("checks", []), args.verification_check)

    review = task.setdefault("review", default_review())
    if args.review_score is not None:
        review["score"] = args.review_score
    if args.review_threshold is not None:
        review["threshold"] = args.review_threshold
    if args.review_last_result is not None:
        review["lastResult"] = args.review_last_result
    if args.review_check:
        append_unique(review.setdefault("checks", []), args.review_check)
    if args.review_finding_json:
        findings = review.setdefault("findings", [])
        for raw in args.review_finding_json:
            finding = parse_review_finding(raw)
            if finding not in findings:
                findings.append(finding)
    if args.review_report_ref is not None:
        review["reportRef"] = args.review_report_ref


def validate_manifest(manifest: dict, schema: dict) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda err: list(err.absolute_path))
    if errors:
        lines = []
        for err in errors:
            loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
            lines.append(f"{loc}: {err.message}")
        raise UpdateTaskError("schema validation failed:\n" + "\n".join(lines))

    tasks = manifest.get("tasks", [])
    ids: set[str] = set()
    for task in tasks:
        task_id = task.get("taskId")
        if task_id in ids:
            raise UpdateTaskError(f"duplicate taskId: {task_id}")
        ids.add(task_id)

    for task in tasks:
        for dependency in task.get("dependsOn", []):
            if dependency not in ids:
                raise UpdateTaskError(f"{task.get('taskId')}: unknown dependsOn: {dependency}")


def validate_done_dependencies(manifest: dict, task: dict) -> None:
    if task.get("status") != "done":
        return

    by_id = {item.get("taskId"): item for item in manifest.get("tasks", [])}
    for dependency in task.get("dependsOn", []):
        dependency_task = by_id.get(dependency)
        if dependency_task is None or dependency_task.get("status") != "done":
            raise UpdateTaskError(f"{task.get('taskId')}: dependsOn {dependency} is not done")


def validate_done_review(task: dict) -> None:
    if task.get("status") != "done":
        return

    review = task.get("review", {})
    if review.get("lastResult") != "passed":
        raise UpdateTaskError(f"{task.get('taskId')}: review.lastResult is not passed")
    if not review.get("checks"):
        raise UpdateTaskError(f"{task.get('taskId')}: review.checks is empty")

    score = review.get("score")
    threshold = review.get("threshold")
    if not isinstance(score, int) or not isinstance(threshold, int):
        raise UpdateTaskError(f"{task.get('taskId')}: review score and threshold must be integers")
    if score < threshold:
        raise UpdateTaskError(
            f"{task.get('taskId')}: review.score {score} is below threshold {threshold}"
        )

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
    if blockers:
        raise UpdateTaskError(
            f"{task.get('taskId')}: review has blocking findings: " + "; ".join(blockers)
        )


def build_updated_manifest(args: argparse.Namespace) -> dict:
    manifest = load_json(args.tasks)
    schema = load_json(args.schema)
    if not isinstance(manifest, dict):
        raise UpdateTaskError(f"{args.tasks} top-level JSON must be an object")

    before = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    task = find_task(manifest, args.task)
    apply_updates(task, args)
    validate_manifest(manifest, schema)
    validate_done_dependencies(manifest, task)
    validate_done_review(task)

    after = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    if before == after:
        raise UpdateTaskError("no task changes requested")

    return manifest


def run(args: argparse.Namespace) -> int:
    if not args.tasks.exists():
        print(f"ERROR: tasks.json not found: {args.tasks}", file=sys.stderr)
        return 2
    if not args.schema.exists():
        print(f"ERROR: schema not found: {args.schema}", file=sys.stderr)
        return 2

    try:
        manifest = build_updated_manifest(args)
    except UpdateTaskError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        atomic_write_json(args.tasks, manifest)
    except OSError as exc:
        print(f"ERROR: failed to write {args.tasks}: {exc}", file=sys.stderr)
        return 2

    print(f"✓ updated {args.task} in {args.tasks}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update one task in Harness tasks.json")
    parser.add_argument("--tasks", type=Path, required=True, help="Path to work/plans/active/<PLAN-ID>/tasks.json")
    parser.add_argument("--schema", type=Path, default=default_schema_path(), help="tasks.schema.json path")
    parser.add_argument("--task", required=True, help="Task ID to update")
    parser.add_argument("--status", choices=STATUS_CHOICES, help="New task status")
    parser.add_argument("--owner-role", choices=OWNER_ROLE_CHOICES, help="New task ownerRole")
    parser.add_argument("--current-step", help="Task currentStep")
    parser.add_argument("--next-action", help="Task nextAction")
    parser.add_argument("--blocked-reason", help="Task blockedReason")
    parser.add_argument("--verification-last-result", choices=VERIFICATION_RESULT_CHOICES,
                        help="verification.lastResult")
    parser.add_argument("--verification-command", action="append", default=[],
                        help="Append a verification command; repeatable")
    parser.add_argument("--verification-check", action="append", default=[],
                        help="Append a verification check; repeatable")
    parser.add_argument("--review-score", type=int, help="review.score")
    parser.add_argument("--review-threshold", type=int, help="review.threshold")
    parser.add_argument("--review-last-result", choices=REVIEW_RESULT_CHOICES,
                        help="review.lastResult")
    parser.add_argument("--review-check", action="append", default=[],
                        help="Append a review check; repeatable")
    parser.add_argument("--review-finding-json", action="append", default=[],
                        help="Append a review finding JSON object; repeatable")
    parser.add_argument("--review-report-ref", help="review.reportRef")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
