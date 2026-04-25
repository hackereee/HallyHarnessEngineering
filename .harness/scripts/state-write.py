#!/usr/bin/env python3
"""
state-write.py

`workflow-state.json` 的唯一写入网关。其他脚本一律只产出 patch，不直接写 state。

流程（与 architecture.md §103 一一对应）：
  1. 读当前 state
  2. 应用 patch（JSON Patch RFC 6902 子集）或 --set 显式字段
  3. 自动刷新 updatedAt（除非 patch 已显式设置）
  4. 调用 validate-state.py 校验合并后的 state
  5. 临时文件 + os.replace 原子落盘
  6. 追加 JSONL 变更日志

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
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


# ---------- 常量 ----------

PHASE_FIELDS_REQUIRING_NEXT_ACTION = ("currentPhase",)


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


def warn_if_phase_changed_without_next_action(before: dict, after: dict) -> list[str]:
    warns: list[str] = []
    for field in PHASE_FIELDS_REQUIRING_NEXT_ACTION:
        if before.get(field) != after.get(field):
            if before.get("nextAction") == after.get("nextAction"):
                warns.append(
                    f"{field} 已变更（{before.get(field)!r} → {after.get(field)!r}），"
                    "但 nextAction 未同步刷新；按 workflow-lifecycle.md §8 视为状态滞后"
                )
    return warns


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

    warns = warn_if_phase_changed_without_next_action(before, after)
    for w in warns:
        print(f"⚠ {w}", file=sys.stderr)

    atomic_write_json(state_path, after)

    log_path = args.log or default_log_path(state_path)
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
            "  state-write.py --set currentPhase=implementing --set nextAction='跑 pytest tests/test_login.py'\n"
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
    args = parser.parse_args(list(argv) if argv is not None else None)

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
