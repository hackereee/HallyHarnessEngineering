#!/usr/bin/env python3
"""
state-write.py

The only write gateway for `workflow-state.json`. Other scripts must only
produce patches and must not write state directly.

Flow:
  1. Read current state.
  2. Apply a patch (JSON Patch RFC 6902 subset) or explicit --set fields.
  3. Validate the currentPhase transition path defined by workflow-lifecycle.md.
  4. Refresh updatedAt automatically unless the patch sets it explicitly.
  5. Call validate-state.py on the merged state.
  6. Atomically write through a temp file and os.replace.
  7. Append a JSONL change log entry.

Input modes, mutually exclusive:
  --patch <file>           Read an RFC 6902 JSON Patch array.
  --patch-json '<json>'    Read a JSON Patch string directly.
  --set field=value ...    Write explicit fields; value accepts JSON literals
                           such as 'null', 'true', '"str"', or bare strings.

Exit codes:
  0  write succeeded
  1  invalid patch or validation failed (state unchanged)
  2  runtime error (missing file / JSON parse failure / missing dependency)
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
    print("ERROR: jsonschema>=4.18 is required; run `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


# ---------- Constants ----------

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


# ---------- Basic Utilities ----------

def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"file not found: {path}")
    except json.JSONDecodeError as e:
        die(f"JSON parse failed {path}: {e}")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------- JSON Patch Subset (RFC 6902) ----------
#
# workflow-state is a flat object, so top-level add/replace/remove is enough for
# real write scenarios. test/move/copy are unnecessary for now and are rejected.

_SUPPORTED_OPS = {"add", "replace", "remove"}


def _split_pointer(ptr: str) -> list[str]:
    if ptr == "":
        return []
    if not ptr.startswith("/"):
        raise ValueError(f"invalid JSON Pointer: {ptr!r}")
    return [seg.replace("~1", "/").replace("~0", "~") for seg in ptr[1:].split("/")]


def apply_patch(state: dict, patch: list[dict]) -> dict:
    if not isinstance(patch, list):
        raise ValueError("patch must be an array")
    out = json.loads(json.dumps(state))  # deep copy via json
    for i, op in enumerate(patch):
        if not isinstance(op, dict):
            raise ValueError(f"patch[{i}] is not an object")
        op_name = op.get("op")
        if op_name not in _SUPPORTED_OPS:
            raise ValueError(f"patch[{i}] has unsupported op: {op_name!r} (supported: {sorted(_SUPPORTED_OPS)})")
        path = op.get("path")
        if not isinstance(path, str):
            raise ValueError(f"patch[{i}] is missing path")
        segs = _split_pointer(path)
        if len(segs) != 1:
            raise ValueError(
                f"patch[{i}] path={path!r}: state-write.py supports only top-level field operations"
            )
        key = segs[0]
        if op_name in ("add", "replace"):
            if "value" not in op:
                raise ValueError(f"patch[{i}] {op_name} is missing value")
            out[key] = op["value"]
        elif op_name == "remove":
            out.pop(key, None)
    return out


# ---------- --set Parsing ----------

def parse_set_assignments(items: list[str]) -> list[dict]:
    """Translate ['field=value', ...] into equivalent replace JSON Patch operations."""
    patch: list[dict] = []
    for raw in items:
        if "=" not in raw:
            raise ValueError(f"--set must use field=value form, got {raw!r}")
        key, _, val = raw.partition("=")
        key = key.strip()
        val = val.strip()
        if not key:
            raise ValueError(f"--set field name is empty: {raw!r}")
        try:
            parsed: Any = json.loads(val)
        except json.JSONDecodeError:
            # Allow unquoted bare strings for command-line ergonomics.
            parsed = val
        patch.append({"op": "replace", "path": f"/{key}", "value": parsed})
    return patch


# ---------- Validation ----------

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
        return None, f"file not found: {path}"
    except json.JSONDecodeError as e:
        return None, f"JSON parse failed {path}: {e}"


def validate_json_schema(data: Any, schema: dict, *, label: str) -> list[str]:
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
        errors.append(f"{label} schema validation failed: {loc}: {err.message}")
    return errors


def tasks_schema_path(workflow_schema_path: Path) -> Path:
    return workflow_schema_path.resolve().parent / "tasks.schema.json"


def tasks_file_from_active_plan(state_path: Path, state: dict) -> tuple[Path | None, list[str]]:
    plan_ref = state.get("activePlanRef")
    if not isinstance(plan_ref, str) or not plan_ref.strip():
        return None, ["reviewing -> archiving applies only to an L2/L3 active plan; activePlanRef must not be empty"]

    plan_file = (state_path.resolve().parent / plan_ref).resolve()
    if plan_file.name != "plan.md":
        return None, [f"reviewing -> archiving requires activePlanRef to point to plan.md: {plan_ref!r}"]
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
        errors.append("reviewing -> archiving requires activeTaskId to exist before the write")

    tasks_file, path_errors = tasks_file_from_active_plan(state_path, before)
    errors += path_errors
    if tasks_file is None:
        return errors

    manifest, manifest_error = load_json_for_validation(tasks_file)
    if manifest_error:
        errors.append(f"reviewing -> archiving cannot read tasks.json: {manifest_error}")
        return errors
    if not isinstance(manifest, dict):
        errors.append(f"reviewing -> archiving requires {tasks_file} top-level JSON to be an object")
        return errors

    schema_file = tasks_schema_path(workflow_schema_path)
    schema, schema_error = load_json_for_validation(schema_file)
    if schema_error:
        errors.append(f"reviewing -> archiving cannot read tasks schema: {schema_error}")
        return errors
    if not isinstance(schema, dict):
        errors.append(f"reviewing -> archiving requires {schema_file} top-level JSON to be an object")
        return errors

    errors += validate_json_schema(manifest, schema, label=str(tasks_file))

    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        errors.append(f"reviewing -> archiving requires {tasks_file} to contain a tasks array")
        return errors

    active_task = None
    for task in tasks:
        if isinstance(task, dict) and task.get("taskId") == active_task_id:
            active_task = task
            break
    if active_task is None:
        errors.append(f"reviewing -> archiving requires activeTaskId={active_task_id!r} to exist in {tasks_file}")
    elif active_task.get("status") != "done":
        errors.append(
            "reviewing -> archiving requires the current active task to be done; "
            f"{active_task_id} currently has status={active_task.get('status')!r}"
        )

    unfinished = [
        f"{task.get('taskId', '<missing-taskId>')}:{task.get('status', '<missing-status>')}"
        for task in tasks
        if isinstance(task, dict) and task.get("status") != "done"
    ]
    if unfinished:
        errors.append(
            "reviewing -> archiving requires all tasks in the plan to be done; "
            f"unfinished: {', '.join(unfinished)}"
        )

    return errors


# ---------- Atomic Write ----------

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


# ---------- Change Log ----------

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
    # Default location under work/: work/sessions/YYYY-MM-DD/state-changes.jsonl
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


# ---------- Main Flow ----------

def build_patch(args: argparse.Namespace) -> list[dict]:
    sources = [bool(args.patch), bool(args.patch_json), bool(args.set)]
    if sum(sources) == 0:
        raise ValueError("one of --patch / --patch-json / --set is required")
    if sum(sources) > 1:
        raise ValueError("--patch / --patch-json / --set are mutually exclusive; use only one")

    if args.patch:
        return load_json(args.patch)
    if args.patch_json:
        try:
            return json.loads(args.patch_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"--patch-json parse failed: {e}")
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
                    f"{field} changed ({before.get(field)!r} -> {after.get(field)!r}), "
                    "but nextAction was not refreshed; workflow-lifecycle.md section 8 treats this as stale state"
                )
            if not patch_touches_field(patch, "ownerRole"):
                warns.append(
                    f"{field} changed ({before.get(field)!r} -> {after.get(field)!r}), "
                    "but ownerRole was not explicitly refreshed; workflow-lifecycle.md section 3.1 treats this as unclear role handoff"
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
        "Illegal phase transition: "
        f"currentPhase cannot change directly from {before_phase!r} to {after_phase!r}; "
        "follow the path defined in workflow-lifecycle.md"
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
        return [f"planned workflow reset requires activePlanRef to point to plan.md: {plan_ref!r}"]
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"planned workflow reset points to a missing plan.md: {plan_path}"]
    section = plan_review_gate_section(plan_text)
    if section is None:
        return ["planned workflow reset requires plan.md to contain ## Plan Review Gate"]
    if not PLAN_REVIEW_PASSED_RE.search(section):
        return ["planned workflow reset requires Plan Review Gate to be Status: passed"]
    return []


def validate_terminal_reset(before: dict, after: dict, patch: list[dict], state_path: Path) -> list[str]:
    errors: list[str] = []

    if before.get("workflowStatus") not in TERMINAL_WORKFLOW_STATUSES:
        errors.append("terminal reset can start only from workflowStatus=completed/archived")
    if before.get("activePlanRef") is not None or before.get("activeTaskId") is not None:
        errors.append("terminal reset requires the old workflow to hold no activePlanRef or activeTaskId")
    if after.get("workflowStatus") != "active":
        errors.append("terminal reset target workflowStatus must be active")
    if after.get("workflowId") == before.get("workflowId"):
        errors.append("terminal reset must use a new workflowId; reusing the old workflowId is forbidden")

    for field in TERMINAL_RESET_REQUIRED_FIELDS:
        if not patch_touches_field(patch, field):
            errors.append(f"terminal reset must explicitly write {field}")

    phase = after.get("currentPhase")
    if phase == "implementing":
        if after.get("ownerRole") != "developer":
            errors.append("direct workflow reset requires ownerRole=developer")
        if after.get("activePlanRef") is not None or after.get("activeTaskId") is not None:
            errors.append("direct workflow reset requires activePlanRef=null and activeTaskId=null")
    elif phase == "planning":
        if after.get("ownerRole") != "planner":
            errors.append("planned workflow reset requires ownerRole=planner")
        if not isinstance(after.get("activePlanRef"), str):
            errors.append("planned workflow reset requires activePlanRef to point to an active plan")
        if after.get("activeTaskId") is not None:
            errors.append("planned workflow reset requires activeTaskId=null")
        errors += validate_planned_reset_plan_review_gate(after, state_path)
    else:
        errors.append("terminal reset target currentPhase must be implementing or planning")

    return errors


def validate_workflow_id_immutable(before: dict, after: dict, *, terminal_reset: bool) -> list[str]:
    if terminal_reset:
        return []
    if before.get("workflowId") != after.get("workflowId"):
        return [
            "workflowId cannot be modified inside the current workflow after creation; "
            "starting a new workflow requires terminal reset with an explicit new workflowId"
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
            errors.append(f"terminal close must explicitly write {field}")

    if after.get("activePlanRef") is not None or after.get("activeTaskId") is not None:
        errors.append("terminal close requires activePlanRef=null and activeTaskId=null")

    active_dirs = active_plan_dirs_for_state(state_path)
    if active_dirs:
        names = ", ".join(path.name for path in active_dirs)
        errors.append(
            "terminal close requires work/plans/active/ to contain no active plan; "
            f"current active plans: {names}"
        )

    if target_status == "completed":
        if after.get("currentPhase") != "reviewing" or after.get("ownerRole") != "reviewer":
            errors.append("completed terminal close requires currentPhase=reviewing and ownerRole=reviewer")
        if before.get("activePlanRef") is not None or before.get("activeTaskId") is not None:
            errors.append("completed terminal close applies only to L0/L1 direct workflows")
    elif target_status == "archived":
        if after.get("currentPhase") != "archiving" or after.get("ownerRole") != "developer":
            errors.append("archived terminal close requires currentPhase=archiving and ownerRole=developer")
    else:
        errors.append(f"terminal close target workflowStatus is unsupported: {target_status!r}")

    return errors


def run(args: argparse.Namespace) -> int:
    state_path: Path = args.state
    schema_path: Path = args.schema
    validate_script: Path = args.validator

    if not state_path.exists():
        die(f"state file not found: {state_path} (the first state must be created by session-start.py / template copy)")

    try:
        patch = build_patch(args)
    except ValueError as e:
        print(f"✗ patch construction failed: {e}", file=sys.stderr)
        return 1

    before = load_json(state_path)
    if not isinstance(before, dict):
        die(f"{state_path} top-level JSON is not an object; cannot apply patch")

    try:
        after = apply_patch(before, patch)
    except ValueError as e:
        print(f"✗ patch application failed: {e}", file=sys.stderr)
        return 1

    terminal_reset = False
    terminal_close = False
    transition_errors: list[str] = []
    terminal_reopen = is_terminal_reopen(before, after)
    terminal_closing = is_terminal_close(before, after)
    if terminal_reopen and not args.allow_terminal_reset:
        transition_errors = [
            "terminal reset requires explicit --allow-terminal-reset; "
            "reopening a completed/archived workflow through a partial workflowStatus patch is forbidden"
        ]
    elif args.allow_terminal_reset and terminal_reopen:
        reset_errors = validate_terminal_reset(before, after, patch, state_path)
        if reset_errors:
            transition_errors = reset_errors
        else:
            terminal_reset = True
    elif terminal_closing and not args.allow_terminal_close:
        transition_errors = [
            "terminal close requires explicit --allow-terminal-close; "
            "bypassing complete-workflow.py or archive-plan.py with a partial workflowStatus patch is forbidden"
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
        print("✗ lifecycle validation failed; state unchanged:", file=sys.stderr)
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
        print("✗ lifecycle preconditions failed; state unchanged:", file=sys.stderr)
        for error in precondition_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    # Refresh updatedAt automatically unless the patch sets it explicitly.
    touched_updated_at = any(
        op.get("path") == "/updatedAt" for op in patch if isinstance(op, dict)
    )
    if not touched_updated_at:
        after["updatedAt"] = now_iso()

    if before == after:
        print("· state unchanged; skipping write")
        return 0

    # Dry-run: write to a temp state, validate it, then decide whether to replace.
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
        print("✗ validation failed; state unchanged:", file=sys.stderr)
        print(out, file=sys.stderr)
        return 1

    warns = warn_if_phase_changed_without_lifecycle_fields(before, after, patch)
    for w in warns:
        print(f"⚠ {w}", file=sys.stderr)

    log_path = args.log or default_log_path(state_path)
    try:
        ensure_change_log_writable(log_path)
    except OSError as exc:
        print(f"✗ change log is not writable; state unchanged: {exc}", file=sys.stderr)
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

    print(f"✓ {state_path} updated ({len(diff_top_level(before, after))} field change(s))")
    print(f"  log: {log_path}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    repo_root = here.parent.parent  # .harness/scripts/ -> repo root
    default_state = repo_root / "work" / "workflow-state.json"
    default_schema = repo_root / ".harness" / "schemas" / "workflow-state.schema.json"
    default_validator = here / "validate-state.py"

    parser = argparse.ArgumentParser(
        description="Only write gateway for workflow-state.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  state-write.py --set currentPhase=implementing --set ownerRole=developer --set nextAction='Run pytest tests/test_login.py'\n"
            "  state-write.py --patch patch.json --source select-next-task --reason 'switch to TASK-002'\n"
            "  echo '[{\"op\":\"replace\",\"path\":\"/workflowStatus\",\"value\":\"completed\"}]' "
            "| state-write.py --patch /dev/stdin\n"
        ),
    )
    parser.add_argument("--state", type=Path, default=default_state, help="workflow-state.json path")
    parser.add_argument("--schema", type=Path, default=default_schema, help="schema path")
    parser.add_argument("--validator", type=Path, default=default_validator, help="validate-state.py path")
    parser.add_argument("--patch", type=Path, help="JSON Patch file path")
    parser.add_argument("--patch-json", help="JSON Patch string")
    parser.add_argument("--set", action="append", default=[], metavar="field=value",
                        help="Explicit field write; repeatable. value accepts JSON literals or bare strings")
    parser.add_argument("--log", type=Path, help="Change log output path (default work/sessions/<date>/state-changes.jsonl)")
    parser.add_argument("--source", help="Caller identifier (for example select-next-task.py) written to the log")
    parser.add_argument("--reason", help="Change reason written to the log")
    parser.add_argument(
        "--allow-terminal-reset",
        action="store_true",
        help="Allow explicit transition from completed/archived terminal workflow to a new active workflow",
    )
    parser.add_argument(
        "--allow-terminal-close",
        action="store_true",
        help="Allow explicit closeout from active workflow to completed/archived terminal state",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
