#!/usr/bin/env python3
"""
archive-plan.py

Archive a completed active plan package to work/plans/archived/<PLAN-ID>/.

Boundary:
  - Requires the LLM to have written a structurally complete closure.md.
  - Performs only deterministic validation, directory migration, and workflow-state patching.
  - workflow-state.json writes still go through state-write.py.
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
        raise ArchiveError(f"{label} failed:\n{output}")
    return output


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArchiveError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ArchiveError(f"JSON parse failed {path}: {exc}") from exc


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
        raise ArchiveError("jsonschema>=4.18 is required; run `pip install jsonschema`") from exc

    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda err: list(err.absolute_path))
    if errors:
        lines: list[str] = []
        for err in errors:
            loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
            lines.append(f"{loc}: {err.message}")
        raise ArchiveError("tasks.json schema validation failed:\n" + "\n".join(lines))
    return manifest


def validate_closure(path: Path) -> None:
    if not path.exists():
        raise ArchiveError(f"closure.md must be written by the Agent before archiving: {path}")
    text = path.read_text(encoding="utf-8")
    missing = [section for section in CLOSURE_REQUIRED_SECTIONS if section not in text]
    if missing:
        raise ArchiveError(f"closure.md is missing required sections: {', '.join(missing)}")


def find_harness_root(root: Path) -> Path:
    candidate = root.resolve()
    if candidate.is_file():
        candidate = candidate.parent

    for current in (candidate, *candidate.parents):
        if (current / ".harness" / "scripts" / "lint-harness.py").exists() and (current / "work").exists():
            return current

    raise ArchiveError(f"cannot locate Harness root from {root}; expected a directory containing .harness/ and work/")


def git_top_level(root: Path) -> Path:
    rc, output = run_command(["git", "rev-parse", "--show-toplevel"], root)
    if rc != 0:
        raise ArchiveError(f"archive-plan requires a Git repository to verify the commit-task gate:\n{output}")
    return Path(output.strip()).resolve()


def normalize_root(root: Path) -> Path:
    harness_root = find_harness_root(root)
    git_top_level(harness_root)
    return harness_root


def path_relative_to_git(path: Path, git_root: Path) -> str:
    try:
        return path.resolve().relative_to(git_root.resolve()).as_posix()
    except ValueError as exc:
        raise ArchiveError(f"path is not inside the Git worktree: {path}") from exc


def changed_paths(git_root: Path) -> list[str]:
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=git_root, text=True, capture_output=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise ArchiveError(f"git status failed:\n{output.strip()}")
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
    git_root = git_top_level(root)
    allowed = {path_relative_to_git(root / "work" / "plans" / "active" / plan_id / "closure.md", git_root)}
    dirty = [path for path in changed_paths(git_root) if path not in allowed]
    if dirty:
        formatted = ", ".join(dirty)
        raise ArchiveError(
            "commit-task.py must commit the completed task before archiving; "
            f"non-closure uncommitted changes remain: {formatted}"
        )


def validate_archive_preconditions(root: Path, plan_id: str) -> tuple[Path, Path]:
    plan_dir = active_plan_dir(root, plan_id)
    archive_dir = archived_plan_dir(root, plan_id)
    if not plan_dir.exists() or not plan_dir.is_dir():
        raise ArchiveError(f"active plan does not exist: {plan_dir}")
    if archive_dir.exists():
        raise ArchiveError(f"archived plan already exists: {archive_dir}")

    state = load_json(state_path(root))
    expected_ref = f"./plans/active/{plan_id}/plan.md"
    if state.get("workflowStatus") != "active":
        raise ArchiveError("workflowStatus must be active before archiving")
    if state.get("currentPhase") != "archiving":
        raise ArchiveError("currentPhase must be archiving before archiving")
    if state.get("ownerRole") != "developer":
        raise ArchiveError("ownerRole must be developer before archiving")
    if state.get("activeTaskId") is not None:
        raise ArchiveError("activeTaskId must be null before archiving")
    if state.get("activePlanRef") != expected_ref:
        raise ArchiveError(f"activePlanRef must be {expected_ref}")

    for filename in ("plan.md", "tasks.json", "handoff.md", "closure.md"):
        if not (plan_dir / filename).exists():
            raise ArchiveError(f"active plan package is missing {filename}: {plan_dir / filename}")

    validate_closure(plan_dir / "closure.md")
    manifest = validate_tasks_schema(root, plan_dir / "tasks.json")
    not_done = [
        task.get("taskId", "<unknown>")
        for task in manifest.get("tasks", [])
        if isinstance(task, dict) and task.get("status") != "done"
    ]
    if not_done:
        raise ArchiveError(f"tasks are still not done; archiving is forbidden: {', '.join(not_done)}")

    validate_commit_task_gate(root, plan_id)
    return plan_dir, archive_dir


def patch_archived_state(root: Path) -> None:
    patch = [
        {"op": "replace", "path": "/workflowStatus", "value": "archived"},
        {"op": "replace", "path": "/activePlanRef", "value": None},
        {"op": "replace", "path": "/activeTaskId", "value": None},
        {"op": "replace", "path": "/nextAction", "value": "Start next workflow"},
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
    parser.add_argument("--root", type=Path, default=repo_root, help="Path inside Harness root; Git top-level may be a parent")
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
