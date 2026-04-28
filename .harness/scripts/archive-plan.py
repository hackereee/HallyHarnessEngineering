#!/usr/bin/env python3
"""
archive-plan.py

将完成的 active plan package 归档到 work/plans/archived/<PLAN-ID>/。

边界：
  - 要求 LLM 已写好结构完整的 closure.md。
  - 只做确定性校验、目录迁移和 workflow-state patch。
  - workflow-state.json 的写入仍通过 state-write.py。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


CLOSURE_REQUIRED_SECTIONS = (
    "## Delivered",
    "## Verification Evidence",
    "## Review Summary",
    "## Architecture Impact",
    "## Deviations",
    "## Follow-ups",
)


class ArchiveError(Exception):
    pass


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def run_checked(label: str, command: list[str], cwd: Path) -> str:
    rc, output = run_command(command, cwd)
    if rc != 0:
        raise ArchiveError(f"{label} 失败:\n{output}")
    return output


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArchiveError(f"文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ArchiveError(f"JSON 解析失败 {path}: {exc}") from exc


def script_path(root: Path, name: str) -> Path:
    return root / ".harness" / "scripts" / name


def state_path(root: Path) -> Path:
    return root / "work" / "workflow-state.json"


def workflow_schema(root: Path) -> Path:
    return root / ".harness" / "schemas" / "workflow-state.schema.json"


def tasks_schema(root: Path) -> Path:
    return root / ".harness" / "schemas" / "tasks.schema.json"


def active_plan_dir(root: Path, plan_id: str) -> Path:
    return root / "work" / "plans" / "active" / plan_id


def archived_plan_dir(root: Path, plan_id: str) -> Path:
    return root / "work" / "plans" / "archived" / plan_id


def run_lint(root: Path) -> None:
    run_checked(
        "lint-harness.py",
        [sys.executable, str(script_path(root, "lint-harness.py")), "--root", str(root)],
        root,
    )


def run_validate_state(root: Path) -> None:
    run_checked(
        "validate-state.py",
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


def validate_tasks_schema(root: Path, tasks_path: Path) -> dict:
    manifest = load_json(tasks_path)
    schema = load_json(tasks_schema(root))
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ArchiveError("需要 jsonschema>=4.18，请执行 `pip install jsonschema`") from exc

    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda err: list(err.absolute_path))
    if errors:
        lines: list[str] = []
        for err in errors:
            loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
            lines.append(f"{loc}: {err.message}")
        raise ArchiveError("tasks.json schema 校验失败:\n" + "\n".join(lines))
    return manifest


def validate_closure(path: Path) -> None:
    if not path.exists():
        raise ArchiveError(f"归档前必须先由 Agent 写入 closure.md: {path}")
    text = path.read_text(encoding="utf-8")
    missing = [section for section in CLOSURE_REQUIRED_SECTIONS if section not in text]
    if missing:
        raise ArchiveError(f"closure.md 缺少必要章节: {', '.join(missing)}")


def ensure_git_root(root: Path) -> None:
    rc, output = run_command(["git", "rev-parse", "--show-toplevel"], root)
    if rc != 0:
        raise ArchiveError(f"archive-plan 需要 Git 仓库以验证 commit-task gate:\n{output}")
    if Path(output.strip()).resolve() != root.resolve():
        raise ArchiveError(f"--root 必须是 Git 顶层目录: {root}")


def normalize_root(root: Path) -> Path:
    rc, output = run_command(["git", "rev-parse", "--show-toplevel"], root)
    if rc != 0:
        raise ArchiveError(f"archive-plan 需要 Git 仓库以定位 Harness root:\n{output}")
    return Path(output.strip()).resolve()


def changed_paths(root: Path) -> list[str]:
    output = run_checked("git status", ["git", "status", "--porcelain"], root)
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            paths.append(path)
        else:
            paths.append(path.strip())
    return paths


def validate_commit_task_gate(root: Path, plan_id: str) -> None:
    ensure_git_root(root)
    allowed = {f"work/plans/active/{plan_id}/closure.md"}
    dirty = [path for path in changed_paths(root) if path not in allowed]
    if dirty:
        formatted = ", ".join(dirty)
        raise ArchiveError(
            "归档前必须先运行 commit-task.py 提交已完成 task；"
            f"当前仍有非 closure 未提交变更: {formatted}"
        )


def validate_archive_preconditions(root: Path, plan_id: str) -> tuple[Path, Path]:
    plan_dir = active_plan_dir(root, plan_id)
    archive_dir = archived_plan_dir(root, plan_id)
    if not plan_dir.exists() or not plan_dir.is_dir():
        raise ArchiveError(f"active plan 不存在: {plan_dir}")
    if archive_dir.exists():
        raise ArchiveError(f"archived plan 已存在: {archive_dir}")

    state = load_json(state_path(root))
    expected_ref = f"./plans/active/{plan_id}/plan.md"
    if state.get("workflowStatus") != "active":
        raise ArchiveError("归档前 workflowStatus 必须为 active")
    if state.get("currentPhase") != "archiving":
        raise ArchiveError("归档前 currentPhase 必须为 archiving")
    if state.get("ownerRole") != "developer":
        raise ArchiveError("归档前 ownerRole 必须为 developer")
    if state.get("activeTaskId") is not None:
        raise ArchiveError("归档前 activeTaskId 必须为 null")
    if state.get("activePlanRef") != expected_ref:
        raise ArchiveError(f"activePlanRef 必须为 {expected_ref}")

    for filename in ("plan.md", "tasks.json", "handoff.md", "closure.md"):
        if not (plan_dir / filename).exists():
            raise ArchiveError(f"active plan package 缺少 {filename}: {plan_dir / filename}")

    validate_closure(plan_dir / "closure.md")
    manifest = validate_tasks_schema(root, plan_dir / "tasks.json")
    not_done = [
        task.get("taskId", "<unknown>")
        for task in manifest.get("tasks", [])
        if isinstance(task, dict) and task.get("status") != "done"
    ]
    if not_done:
        raise ArchiveError(f"仍有 task 未 done，禁止归档: {', '.join(not_done)}")

    validate_commit_task_gate(root, plan_id)
    return plan_dir, archive_dir


def patch_archived_state(root: Path) -> None:
    patch = [
        {"op": "replace", "path": "/workflowStatus", "value": "archived"},
        {"op": "replace", "path": "/activePlanRef", "value": None},
        {"op": "replace", "path": "/activeTaskId", "value": None},
        {"op": "replace", "path": "/nextAction", "value": "开启下一个 workflow"},
    ]
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
            "archive-plan.py",
            "--reason",
            "archive active plan package",
            "--allow-terminal-close",
        ],
        root,
    )


def move_plan(plan_dir: Path, archive_dir: Path) -> None:
    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(plan_dir, archive_dir)


def restore_plan(plan_dir: Path, archive_dir: Path) -> None:
    if archive_dir.exists() and not plan_dir.exists():
        os.replace(archive_dir, plan_dir)


def archive(root: Path, plan_id: str) -> dict:
    root = normalize_root(root)
    run_lint(root)
    run_validate_state(root)
    plan_dir, archive_dir = validate_archive_preconditions(root, plan_id)

    move_plan(plan_dir, archive_dir)
    try:
        patch_archived_state(root)
    except Exception:
        restore_plan(plan_dir, archive_dir)
        raise

    run_lint(root)
    run_validate_state(root)
    return {
        "planId": plan_id,
        "from": str(plan_dir),
        "to": str(archive_dir),
        "workflowStatus": "archived",
    }


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Archive a completed Harness active plan")
    parser.add_argument("--root", type=Path, default=repo_root, help="Path inside repository; normalized to Git top-level")
    parser.add_argument("plan_id", help="Plan id, e.g. PLAN-001")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = archive(args.root.resolve(), args.plan_id)
    except ArchiveError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (OSError, shutil.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
