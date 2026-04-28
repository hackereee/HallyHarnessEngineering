#!/usr/bin/env python3
"""
state-write.py

`workflow-state.json` 的唯一写入网关。其他脚本一律只产出 patch，不直接写 state。

流程（与 architecture.md §103 一一对应）：
  1. 读当前 state
  2. 应用 patch（JSON Patch RFC 6902 子集）或 --set 显式字段
  3. 校验 workflow-lifecycle.md 定义的 currentPhase 转换路径
  4. 自动刷新 updatedAt（除非 patch 已显式设置）
  5. 调用 validate-state.py 校验合并后的 state
  6. 临时文件 + os.replace 原子落盘
  7. 追加 JSONL 变更日志

输入模式（互斥）：
  --patch <file>           读取 RFC 6902 JSON Patch（数组）
  --patch-json '<json>'    直接传入 JSON Patch 字符串
  --set field=value ...    显式字段写入；value 形如 'null'、'true'、'"str"'、JSON 字面量

退出码：
  0  写入成功
  1  patch 无效或校验失败（state 未改动）
  2  运行错误（文件缺失 / JSON 解析失败 / 依赖缺失）
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

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: 需要 jsonschema>=4.18，请执行 `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


# ---------- 常量 ----------

PHASE_FIELDS_REQUIRING_NEXT_ACTION = ("currentPhase",)

ALLOWED_PHASE_TRANSITIONS = {
    ("planning", "implementing"),
    ("implementing", "testing"),
    ("testing", "reviewing"),
    ("reviewing", "implementing"),
    ("reviewing", "archiving"),
    # Scope redefinition path; semantic justification must be recorded in handoff.
    ("implementing", "planning"),
}

TERMINAL_WORKFLOW_STATUSES = {"completed", "archived"}
TERMINAL_RESET_REQUIRED_FIELDS = (
    "workflowId",
    "workflowStatus",
    "activePlanRef",
    "activeTaskId",
    "currentPhase",
    "ownerRole",
    "nextAction",
)
TERMINAL_CLOSE_REQUIRED_FIELDS = (
    "workflowStatus",
    "activePlanRef",
    "activeTaskId",
    "nextAction",
)
PLAN_REVIEW_HEADING_RE = re.compile(r"(?m)^##\s+Plan Review Gate\s*$")
PLAN_REVIEW_PASSED_RE = re.compile(r"(?mi)^Status:\s*passed\s*$")
H2_HEADING_RE = re.compile(r"(?m)^##\s+")


# ---------- 基础工具 ----------

def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"文件不存在: {path}")
    except json.JSONDecodeError as e:
        die(f"JSON 解析失败 {path}: {e}")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------- JSON Patch 子集（RFC 6902） ----------
#
# workflow-state 是扁平对象，这里只实现顶层路径的 add/replace/remove，足够覆盖
# 所有现实写入场景。test/move/copy 暂不需要，遇到则报错。

_SUPPORTED_OPS = {"add", "replace", "remove"}


def _split_pointer(ptr: str) -> list[str]:
    if ptr == "":
        return []
    if not ptr.startswith("/"):
        raise ValueError(f"非法 JSON Pointer: {ptr!r}")
    return [seg.replace("~1", "/").replace("~0", "~") for seg in ptr[1:].split("/")]


def apply_patch(state: dict, patch: list[dict]) -> dict:
    if not isinstance(patch, list):
        raise ValueError("patch 必须是数组")
    out = json.loads(json.dumps(state))  # deep copy via json
    for i, op in enumerate(patch):
        if not isinstance(op, dict):
            raise ValueError(f"patch[{i}] 不是对象")
        op_name = op.get("op")
        if op_name not in _SUPPORTED_OPS:
            raise ValueError(f"patch[{i}] 不支持的操作: {op_name!r}（仅支持 {sorted(_SUPPORTED_OPS)}）")
        path = op.get("path")
        if not isinstance(path, str):
            raise ValueError(f"patch[{i}] 缺少 path")
        segs = _split_pointer(path)
        if len(segs) != 1:
            raise ValueError(
                f"patch[{i}] path={path!r}：state-write.py 仅支持顶层字段操作"
            )
        key = segs[0]
        if op_name in ("add", "replace"):
            if "value" not in op:
                raise ValueError(f"patch[{i}] {op_name} 缺少 value")
            out[key] = op["value"]
        elif op_name == "remove":
            out.pop(key, None)
    return out


# ---------- --set 解析 ----------

def parse_set_assignments(items: list[str]) -> list[dict]:
    """把 ['field=value', ...] 翻译成等价的 JSON Patch（replace）。"""
    patch: list[dict] = []
    for raw in items:
        if "=" not in raw:
            raise ValueError(f"--set 需为 field=value 形式，收到 {raw!r}")
        key, _, val = raw.partition("=")
        key = key.strip()
        val = val.strip()
        if not key:
            raise ValueError(f"--set 字段名为空: {raw!r}")
        try:
            parsed: Any = json.loads(val)
        except json.JSONDecodeError:
            # 允许不带引号的裸字符串（便于命令行使用）
            parsed = val
        patch.append({"op": "replace", "path": f"/{key}", "value": parsed})
    return patch


# ---------- 校验 ----------

def run_validate(validate_script: Path, state_path: Path, schema_path: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(validate_script), "--state", str(state_path), "--schema", str(schema_path)],
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def load_json_for_validation(path: Path) -> tuple[Any | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, f"文件不存在: {path}"
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败 {path}: {e}"


def validate_json_schema(data: Any, schema: dict, *, label: str) -> list[str]:
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
        errors.append(f"{label} schema 校验失败: {loc}: {err.message}")
    return errors


def tasks_schema_path(workflow_schema_path: Path) -> Path:
    return workflow_schema_path.resolve().parent / "tasks.schema.json"


def tasks_file_from_active_plan(state_path: Path, state: dict) -> tuple[Path | None, list[str]]:
    plan_ref = state.get("activePlanRef")
    if not isinstance(plan_ref, str) or not plan_ref.strip():
        return None, ["reviewing → archiving 只适用于 L2/L3 active plan；activePlanRef 不能为空"]

    plan_file = (state_path.resolve().parent / plan_ref).resolve()
    if plan_file.name != "plan.md":
        return None, [f"reviewing → archiving 要求 activePlanRef 指向 plan.md: {plan_ref!r}"]
    return plan_file.parent / "tasks.json", []


def validate_reviewing_to_archiving_preconditions(
    before: dict,
    after: dict,
    state_path: Path,
    workflow_schema_path: Path,
) -> list[str]:
    if before.get("currentPhase") != "reviewing" or after.get("currentPhase") != "archiving":
        return []

    errors: list[str] = []
    active_task_id = before.get("activeTaskId")
    if not isinstance(active_task_id, str) or not active_task_id.strip():
        errors.append("reviewing → archiving 要求写入前存在 activeTaskId")

    tasks_file, path_errors = tasks_file_from_active_plan(state_path, before)
    errors += path_errors
    if tasks_file is None:
        return errors

    manifest, manifest_error = load_json_for_validation(tasks_file)
    if manifest_error:
        errors.append(f"reviewing → archiving 无法读取 tasks.json: {manifest_error}")
        return errors
    if not isinstance(manifest, dict):
        errors.append(f"reviewing → archiving 要求 {tasks_file} 顶层为对象")
        return errors

    schema_file = tasks_schema_path(workflow_schema_path)
    schema, schema_error = load_json_for_validation(schema_file)
    if schema_error:
        errors.append(f"reviewing → archiving 无法读取 tasks schema: {schema_error}")
        return errors
    if not isinstance(schema, dict):
        errors.append(f"reviewing → archiving 要求 {schema_file} 顶层为对象")
        return errors

    errors += validate_json_schema(manifest, schema, label=str(tasks_file))

    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        errors.append(f"reviewing → archiving 要求 {tasks_file} 包含 tasks 数组")
        return errors

    active_task = None
    for task in tasks:
        if isinstance(task, dict) and task.get("taskId") == active_task_id:
            active_task = task
            break
    if active_task is None:
        errors.append(f"reviewing → archiving 要求 activeTaskId={active_task_id!r} 存在于 {tasks_file}")
    elif active_task.get("status") != "done":
        errors.append(
            "reviewing → archiving 要求当前 active task 已 done；"
            f"{active_task_id} 当前 status={active_task.get('status')!r}"
        )

    unfinished = [
        f"{task.get('taskId', '<missing-taskId>')}:{task.get('status', '<missing-status>')}"
        for task in tasks
        if isinstance(task, dict) and task.get("status") != "done"
    ]
    if unfinished:
        errors.append(
            "reviewing → archiving 要求 plan 内所有 task 均为 done；"
            f"未完成: {', '.join(unfinished)}"
        )

    return errors


# ---------- 原子落盘 ----------

def atomic_write_json(path: Path, data: Any) -> None:
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


# ---------- 变更日志 ----------

def diff_top_level(before: dict, after: dict) -> dict:
    keys = set(before) | set(after)
    changes: dict[str, dict] = {}
    for k in sorted(keys):
        b = before.get(k, "<absent>")
        a = after.get(k, "<absent>")
        if b != a:
            changes[k] = {"before": b, "after": a}
    return changes


def append_change_log(log_path: Path, entry: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def default_log_path(state_path: Path) -> Path:
    # 默认与 state 同处 work/ 下：work/sessions/YYYY-MM-DD/state-changes.jsonl
    state_dir = state_path.resolve().parent
    today = datetime.now().strftime("%Y-%m-%d")
    return state_dir / "sessions" / today / "state-changes.jsonl"


def ensure_change_log_writable(log_path: Path) -> None:
    if log_path.exists() and log_path.is_dir():
        raise OSError(f"state change log path is a directory: {log_path}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=log_path.name + ".", suffix=".tmp", dir=log_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


# ---------- 主流程 ----------

def build_patch(args: argparse.Namespace) -> list[dict]:
    sources = [bool(args.patch), bool(args.patch_json), bool(args.set)]
    if sum(sources) == 0:
        raise ValueError("必须提供 --patch / --patch-json / --set 之一")
    if sum(sources) > 1:
        raise ValueError("--patch / --patch-json / --set 互斥，请只用一种")

    if args.patch:
        return load_json(args.patch)
    if args.patch_json:
        try:
            return json.loads(args.patch_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"--patch-json 解析失败: {e}")
    return parse_set_assignments(args.set)


def patch_touches_field(patch: list[dict], field: str) -> bool:
    expected_path = f"/{field}"
    return any(isinstance(op, dict) and op.get("path") == expected_path for op in patch)


def warn_if_phase_changed_without_lifecycle_fields(
    before: dict,
    after: dict,
    patch: list[dict],
) -> list[str]:
    warns: list[str] = []
    for field in PHASE_FIELDS_REQUIRING_NEXT_ACTION:
        if before.get(field) != after.get(field):
            if before.get("nextAction") == after.get("nextAction"):
                warns.append(
                    f"{field} 已变更（{before.get(field)!r} → {after.get(field)!r}），"
                    "但 nextAction 未同步刷新；按 workflow-lifecycle.md §8 视为状态滞后"
                )
            if not patch_touches_field(patch, "ownerRole"):
                warns.append(
                    f"{field} 已变更（{before.get(field)!r} → {after.get(field)!r}），"
                    "但 ownerRole 未显式刷新；按 workflow-lifecycle.md §3.1 视为责任角色交接不清晰"
                )
    return warns


def validate_phase_transition(before: dict, after: dict) -> list[str]:
    before_phase = before.get("currentPhase")
    after_phase = after.get("currentPhase")
    if before_phase == after_phase:
        return []

    if (before_phase, after_phase) in ALLOWED_PHASE_TRANSITIONS:
        return []

    return [
        "非法阶段流转："
        f"currentPhase 不允许从 {before_phase!r} 直接变为 {after_phase!r}；"
        "请按 workflow-lifecycle.md 的阶段路径流转"
    ]


def is_terminal_reopen(before: dict, after: dict) -> bool:
    return (
        before.get("workflowStatus") in TERMINAL_WORKFLOW_STATUSES
        and before.get("workflowStatus") != after.get("workflowStatus")
        and after.get("workflowStatus") == "active"
    )


def is_terminal_close(before: dict, after: dict) -> bool:
    return (
        before.get("workflowStatus") == "active"
        and after.get("workflowStatus") in TERMINAL_WORKFLOW_STATUSES
        and before.get("workflowStatus") != after.get("workflowStatus")
    )


def plan_review_gate_section(plan_text: str) -> str | None:
    match = PLAN_REVIEW_HEADING_RE.search(plan_text)
    if not match:
        return None
    start = match.end()
    next_heading = H2_HEADING_RE.search(plan_text, start)
    end = next_heading.start() if next_heading else len(plan_text)
    return plan_text[start:end]


def validate_planned_reset_plan_review_gate(after: dict, state_path: Path) -> list[str]:
    plan_ref = after.get("activePlanRef")
    if not isinstance(plan_ref, str):
        return []
    plan_path = (state_path.resolve().parent / plan_ref).resolve()
    if plan_path.name != "plan.md":
        return [f"planned workflow reset 要求 activePlanRef 指向 plan.md: {plan_ref!r}"]
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"planned workflow reset 指向的 plan.md 不存在: {plan_path}"]
    section = plan_review_gate_section(plan_text)
    if section is None:
        return ["planned workflow reset 要求 plan.md 包含 ## Plan Review Gate"]
    if not PLAN_REVIEW_PASSED_RE.search(section):
        return ["planned workflow reset 要求 Plan Review Gate 为 Status: passed"]
    return []


def validate_terminal_reset(before: dict, after: dict, patch: list[dict], state_path: Path) -> list[str]:
    errors: list[str] = []

    if before.get("workflowStatus") not in TERMINAL_WORKFLOW_STATUSES:
        errors.append("terminal reset 只能从 workflowStatus=completed/archived 开始")
    if before.get("activePlanRef") is not None or before.get("activeTaskId") is not None:
        errors.append("terminal reset 要求旧 workflow 不再持有 activePlanRef 或 activeTaskId")
    if after.get("workflowStatus") != "active":
        errors.append("terminal reset 的目标 workflowStatus 必须为 active")
    if after.get("workflowId") == before.get("workflowId"):
        errors.append("terminal reset 必须使用新的 workflowId，禁止复用旧 workflowId")

    for field in TERMINAL_RESET_REQUIRED_FIELDS:
        if not patch_touches_field(patch, field):
            errors.append(f"terminal reset 必须显式写入 {field}")

    phase = after.get("currentPhase")
    if phase == "implementing":
        if after.get("ownerRole") != "developer":
            errors.append("direct workflow reset 要求 ownerRole=developer")
        if after.get("activePlanRef") is not None or after.get("activeTaskId") is not None:
            errors.append("direct workflow reset 要求 activePlanRef=null 且 activeTaskId=null")
    elif phase == "planning":
        if after.get("ownerRole") != "planner":
            errors.append("planned workflow reset 要求 ownerRole=planner")
        if not isinstance(after.get("activePlanRef"), str):
            errors.append("planned workflow reset 要求 activePlanRef 指向 active plan")
        if after.get("activeTaskId") is not None:
            errors.append("planned workflow reset 要求 activeTaskId=null")
        errors += validate_planned_reset_plan_review_gate(after, state_path)
    else:
        errors.append("terminal reset 目标 currentPhase 只能是 implementing 或 planning")

    return errors


def validate_workflow_id_immutable(before: dict, after: dict, *, terminal_reset: bool) -> list[str]:
    if terminal_reset:
        return []
    if before.get("workflowId") != after.get("workflowId"):
        return [
            "workflowId 创建后不允许在当前 workflow 内修改；"
            "开启新 workflow 必须通过 terminal reset 并显式使用新的 workflowId"
        ]
    return []


def active_plan_dirs_for_state(state_path: Path) -> list[Path]:
    active_root = state_path.resolve().parent / "plans" / "active"
    if not active_root.exists() or not active_root.is_dir():
        return []
    return sorted(path for path in active_root.iterdir() if path.is_dir())


def validate_terminal_close(before: dict, after: dict, patch: list[dict], state_path: Path) -> list[str]:
    errors: list[str] = []
    target_status = after.get("workflowStatus")

    for field in TERMINAL_CLOSE_REQUIRED_FIELDS:
        if not patch_touches_field(patch, field):
            errors.append(f"terminal close 必须显式写入 {field}")

    if after.get("activePlanRef") is not None or after.get("activeTaskId") is not None:
        errors.append("terminal close 要求 activePlanRef=null 且 activeTaskId=null")

    active_dirs = active_plan_dirs_for_state(state_path)
    if active_dirs:
        names = ", ".join(path.name for path in active_dirs)
        errors.append(
            "terminal close 要求 work/plans/active/ 不存在 active plan；"
            f"当前仍有 active plan: {names}"
        )

    if target_status == "completed":
        if after.get("currentPhase") != "reviewing" or after.get("ownerRole") != "reviewer":
            errors.append("completed terminal close 要求 currentPhase=reviewing 且 ownerRole=reviewer")
        if before.get("activePlanRef") is not None or before.get("activeTaskId") is not None:
            errors.append("completed terminal close 只适用于 L0/L1 direct workflow")
    elif target_status == "archived":
        if after.get("currentPhase") != "archiving" or after.get("ownerRole") != "developer":
            errors.append("archived terminal close 要求 currentPhase=archiving 且 ownerRole=developer")
    else:
        errors.append(f"terminal close 目标 workflowStatus 不支持: {target_status!r}")

    return errors


def run(args: argparse.Namespace) -> int:
    state_path: Path = args.state
    schema_path: Path = args.schema
    validate_script: Path = args.validator

    if not state_path.exists():
        die(f"state 文件不存在: {state_path}（首个 state 请由 session-start.py / 模板复制创建）")

    try:
        patch = build_patch(args)
    except ValueError as e:
        print(f"✗ patch 构造失败: {e}", file=sys.stderr)
        return 1

    before = load_json(state_path)
    if not isinstance(before, dict):
        die(f"{state_path} 顶层不是对象，无法应用 patch")

    try:
        after = apply_patch(before, patch)
    except ValueError as e:
        print(f"✗ patch 应用失败: {e}", file=sys.stderr)
        return 1

    terminal_reset = False
    terminal_close = False
    transition_errors: list[str] = []
    terminal_reopen = is_terminal_reopen(before, after)
    terminal_closing = is_terminal_close(before, after)
    if terminal_reopen and not args.allow_terminal_reset:
        transition_errors = [
            "terminal reset 必须显式传入 --allow-terminal-reset；"
            "禁止通过局部 workflowStatus patch 重新打开 completed/archived workflow"
        ]
    elif args.allow_terminal_reset and terminal_reopen:
        reset_errors = validate_terminal_reset(before, after, patch, state_path)
        if reset_errors:
            transition_errors = reset_errors
        else:
            terminal_reset = True
    elif terminal_closing and not args.allow_terminal_close:
        transition_errors = [
            "terminal close 必须显式传入 --allow-terminal-close；"
            "禁止通过局部 workflowStatus patch 绕过 complete-workflow.py 或 archive-plan.py"
        ]
    elif terminal_closing and args.allow_terminal_close:
        close_errors = validate_terminal_close(before, after, patch, state_path)
        if close_errors:
            transition_errors = close_errors
        else:
            terminal_close = True

    if not transition_errors:
        transition_errors = validate_workflow_id_immutable(before, after, terminal_reset=terminal_reset)

    if not transition_errors and not terminal_reset and not terminal_close:
        transition_errors = validate_phase_transition(before, after)

    if transition_errors:
        print("✗ lifecycle 校验失败，state 未改动：", file=sys.stderr)
        for error in transition_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    precondition_errors = validate_reviewing_to_archiving_preconditions(
        before,
        after,
        state_path,
        schema_path,
    )
    if precondition_errors:
        print("✗ lifecycle 前置条件失败，state 未改动：", file=sys.stderr)
        for error in precondition_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    # 自动刷新 updatedAt（除非 patch 已显式指定）
    touched_updated_at = any(
        op.get("path") == "/updatedAt" for op in patch if isinstance(op, dict)
    )
    if not touched_updated_at:
        after["updatedAt"] = now_iso()

    if before == after:
        print("· state 无变化，跳过写入")
        return 0

    # 干跑：先写到临时文件让 validate 校验，再决定是否替换
    tmp_state = state_path.with_suffix(state_path.suffix + ".pending")
    try:
        with tmp_state.open("w", encoding="utf-8") as f:
            json.dump(after, f, ensure_ascii=False, indent=2)
            f.write("\n")
        rc, out = run_validate(validate_script, tmp_state, schema_path)
    finally:
        try:
            tmp_state.unlink()
        except FileNotFoundError:
            pass

    if rc != 0:
        print("✗ 校验失败，state 未改动：", file=sys.stderr)
        print(out, file=sys.stderr)
        return 1

    warns = warn_if_phase_changed_without_lifecycle_fields(before, after, patch)
    for w in warns:
        print(f"⚠ {w}", file=sys.stderr)

    log_path = args.log or default_log_path(state_path)
    try:
        ensure_change_log_writable(log_path)
    except OSError as exc:
        print(f"✗ 变更日志不可写，state 未改动: {exc}", file=sys.stderr)
        return 2

    atomic_write_json(state_path, after)

    append_change_log(
        log_path,
        {
            "ts": now_iso(),
            "state": str(state_path),
            "source": args.source or "unknown",
            "reason": args.reason or "",
            "patch": patch,
            "changes": diff_top_level(before, after),
            "warnings": warns,
        },
    )

    print(f"✓ {state_path} 已更新（{len(diff_top_level(before, after))} 个字段变化）")
    print(f"  日志：{log_path}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent  # .harness/scripts/ → repo root
    default_state = repo_root / "work" / "workflow-state.json"
    default_schema = repo_root / ".harness" / "schemas" / "workflow-state.schema.json"
    default_validator = here / "validate-state.py"

    parser = argparse.ArgumentParser(
        description="workflow-state.json 的唯一写入网关",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  state-write.py --set currentPhase=implementing --set ownerRole=developer --set nextAction='跑 pytest tests/test_login.py'\n"
            "  state-write.py --patch patch.json --source select-next-task --reason '切换到 TASK-002'\n"
            "  echo '[{\"op\":\"replace\",\"path\":\"/workflowStatus\",\"value\":\"completed\"}]' "
            "| state-write.py --patch /dev/stdin\n"
        ),
    )
    parser.add_argument("--state", type=Path, default=default_state, help="workflow-state.json 路径")
    parser.add_argument("--schema", type=Path, default=default_schema, help="schema 路径")
    parser.add_argument("--validator", type=Path, default=default_validator, help="validate-state.py 路径")
    parser.add_argument("--patch", type=Path, help="JSON Patch 文件路径")
    parser.add_argument("--patch-json", help="JSON Patch 字符串")
    parser.add_argument("--set", action="append", default=[], metavar="field=value",
                        help="显式字段写入，可重复；value 接受 JSON 字面量或裸字符串")
    parser.add_argument("--log", type=Path, help="变更日志输出路径（默认 work/sessions/<日期>/state-changes.jsonl）")
    parser.add_argument("--source", help="调用方标识（如 select-next-task.py），写入日志便于追溯")
    parser.add_argument("--reason", help="变更原因，写入日志")
    parser.add_argument(
        "--allow-terminal-reset",
        action="store_true",
        help="允许 completed/archived 终态 workflow 显式切换为新的 active workflow",
    )
    parser.add_argument(
        "--allow-terminal-close",
        action="store_true",
        help="允许 active workflow 显式收口到 completed/archived 终态",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
