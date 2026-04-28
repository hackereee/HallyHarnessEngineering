#!/usr/bin/env python3
"""
session-start.py

Harness 会话启动编排器。它只做 preflight、首次 state bootstrap 和会话审计快照；
不激活 task、不推进 currentPhase、不修改已有 workflow-state.json。

退出码：
  0  启动成功
  1  Harness 条件不满足或 state 校验失败
  2  运行错误
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REQUIRED_ASSETS = (
    ".harness/ARCHITECTURE.md",
    ".harness/schemas/workflow-state.schema.json",
    ".harness/schemas/tasks.schema.json",
    ".harness/schemas/backlogs.schema.json",
    ".harness/schemas/backlog-consumption-event.schema.json",
    ".harness/schemas/project-contracts.schema.json",
    ".harness/schemas/project-entrypoints.schema.json",
    ".harness/templates/workflow-state.template.json",
    ".harness/templates/backlogs.template.json",
    ".harness/templates/project-contracts.template.json",
    ".harness/templates/project-entrypoints.template.json",
    ".harness/templates/entrypoint-managed-block.template.md",
    ".harness/templates/plan.template.md",
    ".harness/templates/tasks.template.json",
    ".harness/templates/handoff.template.md",
    ".harness/templates/closure.template.md",
    ".harness/rules/workflow-lifecycle.md",
    ".harness/rules/archive-rules.md",
    ".harness/rules/backlog-rules.md",
    ".harness/rules/handoff-rules.md",
    ".harness/rules/session-start.md",
    ".harness/skills/project-init/SKILL.md",
    ".harness/skills/project-env-contract/SKILL.md",
    ".harness/skills/plan-writing/SKILL.md",
    ".harness/skills/task-review/SKILL.md",
    ".harness/scripts/validate-state.py",
    ".harness/scripts/lint-harness.py",
    ".harness/scripts/state-write.py",
    ".harness/scripts/start-workflow.py",
    ".harness/scripts/update-task.py",
    ".harness/scripts/select-next-task.py",
    ".harness/scripts/materialize-tasks.py",
    ".harness/scripts/lifecycle-transaction.py",
    ".harness/scripts/commit-task.py",
    ".harness/scripts/archive-plan.py",
    ".harness/scripts/complete-workflow.py",
    ".harness/scripts/backlog-intake.py",
    ".harness/scripts/backlog-consume.py",
    ".harness/scripts/check-project-env.py",
    ".harness/scripts/init-project-entrypoint.py",
    ".harness/scripts/harness",
    ".harness/scripts/session-start.py",
)


class SessionStartError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def parse_timestamp(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc).astimezone()
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SessionStartError(f"--timestamp 不是合法 ISO 8601 时间: {raw}", 2) from exc
    if parsed.tzinfo is None:
        raise SessionStartError("--timestamp 必须包含时区，例如 2026-04-27T09:00:00+08:00", 2)
    return parsed


def format_timestamp(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def sanitize_session_id(raw: str | None, dt: datetime) -> str:
    value = raw or dt.strftime("%H%M%S")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", value):
        raise SessionStartError(
            "--session-id 只能包含字母、数字、点、下划线和短横线，且必须以字母或数字开头",
            2,
        )
    return value


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SessionStartError(f"文件不存在: {path}", 2) from exc
    except json.JSONDecodeError as exc:
        raise SessionStartError(f"JSON 解析失败 {path}: {exc}", 2) from exc


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


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def check_required_assets(root: Path) -> list[str]:
    missing: list[str] = []
    for relative in REQUIRED_ASSETS:
        if not (root / relative).exists():
            missing.append(relative)
    return missing


def check_environment(root: Path) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    errors: list[str] = []

    lines.append(f"python: {sys.executable}")
    try:
        import jsonschema  # type: ignore

        version = getattr(jsonschema, "__version__", "unknown")
        lines.append(f"jsonschema: available ({version})")
    except ImportError:
        errors.append("jsonschema 不可用；请安装 jsonschema>=4.18")
        lines.append("jsonschema: missing")

    git_rc, git_version = run_command(["git", "--version"], root)
    if git_rc == 0:
        lines.append(f"git: {git_version}")
    else:
        lines.append(f"git: unavailable ({git_version})")

    return lines, errors


def active_plan_dirs(root: Path) -> list[Path]:
    active_root = root / "work" / "plans" / "active"
    if not active_root.exists() or not active_root.is_dir():
        return []
    return sorted(path for path in active_root.iterdir() if path.is_dir())


def bootstrap_state(root: Path, timestamp: datetime) -> Path:
    state_path = root / "work" / "workflow-state.json"
    if state_path.exists():
        return state_path

    if active_plan_dirs(root):
        names = ", ".join(path.name for path in active_plan_dirs(root))
        raise SessionStartError(
            f"workflow-state.json 不存在但存在 active plan 目录: {names}",
            1,
        )

    template_path = root / ".harness" / "templates" / "workflow-state.template.json"
    state = load_json(template_path)
    state["$schema"] = "../.harness/schemas/workflow-state.schema.json"
    state["workflowId"] = f"workflow-adhoc-{timestamp.strftime('%Y%m%d')}-001"
    state["activePlanRef"] = None
    state["activeTaskId"] = None
    state["workflowStatus"] = "active"
    state["currentPhase"] = "implementing"
    state["ownerRole"] = "developer"
    state["nextAction"] = "判断当前需求的任务等级"
    state["updatedAt"] = format_timestamp(timestamp)

    pending = state_path.with_suffix(state_path.suffix + ".pending")
    atomic_write_json(pending, state)
    validator = root / ".harness" / "scripts" / "validate-state.py"
    schema = root / ".harness" / "schemas" / "workflow-state.schema.json"
    rc, output = run_command(
        [sys.executable, str(validator), "--state", str(pending), "--schema", str(schema)],
        root,
    )
    if rc != 0:
        try:
            pending.unlink()
        except FileNotFoundError:
            pass
        raise SessionStartError(f"初始 workflow-state.json 校验失败:\n{output}", 1)

    os.replace(pending, state_path)
    return state_path


def validate_state(root: Path, state_path: Path) -> tuple[int, str]:
    validator = root / ".harness" / "scripts" / "validate-state.py"
    schema = root / ".harness" / "schemas" / "workflow-state.schema.json"
    return run_command(
        [sys.executable, str(validator), "--state", str(state_path), "--schema", str(schema)],
        root,
    )


def ensure_work_dirs(root: Path, session_date: str) -> None:
    for relative in (
        "work/plans/active",
        "work/plans/archived",
        f"work/sessions/{session_date}",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)


def find_previous_session(root: Path, current_session: Path) -> Path | None:
    sessions_root = root / "work" / "sessions"
    if not sessions_root.exists():
        return None
    candidates = sorted(
        path
        for path in sessions_root.glob("*/session-*.md")
        if path.resolve() != current_session.resolve()
    )
    return candidates[-1] if candidates else None


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def git_status(root: Path) -> str:
    rc, output = run_command(["git", "-C", str(root), "status", "--short", "--branch"], root)
    if rc != 0:
        return f"unavailable: {output}"
    return output or "(clean output unavailable)"


def write_session_file(
    *,
    root: Path,
    session_path: Path,
    timestamp: datetime,
    environment_lines: list[str],
    lint_output: str,
    validate_output: str,
    state: dict,
    previous_session: Path | None,
    bootstrapped: bool,
) -> None:
    previous = rel(previous_session, root) if previous_session else "none"
    git = git_status(root)
    state_lines = [
        f"- workflowId: {state.get('workflowId')}",
        f"- workflowStatus: {state.get('workflowStatus')}",
        f"- currentPhase: {state.get('currentPhase')}",
        f"- ownerRole: {state.get('ownerRole')}",
        f"- activePlanRef: {state.get('activePlanRef')}",
        f"- activeTaskId: {state.get('activeTaskId')}",
        f"- nextAction: {state.get('nextAction')}",
    ]
    content = "\n".join(
        [
            f"# Session {session_path.stem.removeprefix('session-')}",
            "",
            "## Startup Evidence",
            f"- Started at: {format_timestamp(timestamp)}",
            f"- Repo root: {root}",
            f"- Previous session: {previous}",
            "- Harness lint: passed",
            "- Workflow state validation: passed",
            f"- Workflow state bootstrapped: {'yes' if bootstrapped else 'no'}",
            f"- Git status: {git.splitlines()[0] if git else ''}",
            "",
            "## Current Workflow",
            *state_lines,
            "",
            "## Environment",
            *(f"- {line}" for line in environment_lines),
            "",
            "## Command Evidence",
            "",
            "### lint-harness.py",
            "```text",
            lint_output,
            "```",
            "",
            "### validate-state.py",
            "```text",
            validate_output,
            "```",
            "",
            "## Agent Notes",
            "Pending. Agent should append semantic assessment after reading the relevant rules and state.",
            "",
        ]
    )
    session_path.write_text(content, encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    timestamp = parse_timestamp(args.timestamp)
    session_id = sanitize_session_id(args.session_id, timestamp)
    session_date = timestamp.date().isoformat()
    session_path = root / "work" / "sessions" / session_date / f"session-{session_id}.md"

    missing = check_required_assets(root)
    if missing:
        print("✗ Harness 关键工件缺失:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        return 1

    environment_lines, environment_errors = check_environment(root)
    if environment_errors:
        print("✗ 环境检查失败:", file=sys.stderr)
        for error in environment_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    lint_script = root / ".harness" / "scripts" / "lint-harness.py"
    lint_rc, lint_output = run_command([sys.executable, str(lint_script), "--root", str(root)], root)
    if lint_rc != 0:
        print(lint_output, file=sys.stderr)
        return 1

    ensure_work_dirs(root, session_date)
    state_path = root / "work" / "workflow-state.json"
    bootstrapped = not state_path.exists()
    state_path = bootstrap_state(root, timestamp)

    validate_rc, validate_output = validate_state(root, state_path)
    if validate_rc != 0:
        print(validate_output, file=sys.stderr)
        return 1

    state = load_json(state_path)
    previous_session = find_previous_session(root, session_path)
    write_session_file(
        root=root,
        session_path=session_path,
        timestamp=timestamp,
        environment_lines=environment_lines,
        lint_output=lint_output,
        validate_output=validate_output,
        state=state,
        previous_session=previous_session,
        bootstrapped=bootstrapped,
    )

    print(f"✓ session-start 完成: {rel(session_path, root)}")
    print(f"NEXT_ACTION={state.get('nextAction')}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Start a Harness session")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument("--session-id", help="Session id used in session-<id>.md")
    parser.add_argument("--timestamp", help="ISO 8601 timestamp with timezone")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        return run(args)
    except SessionStartError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
