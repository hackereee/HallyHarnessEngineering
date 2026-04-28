#!/usr/bin/env python3
"""
check-project-env.py

Generic project environment checker. The project contract is the truth source;
this runner validates and executes declared checks without inventing project
requirements and without writing Harness runtime state.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: 需要 jsonschema>=4.18，请执行 `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


class CheckProjectEnvError(Exception):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CheckProjectEnvError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CheckProjectEnvError(f"JSON parse failed {path}: {exc}") from exc


def validate_contract(contract: dict, schema: dict) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(contract), key=lambda err: list(err.absolute_path))
    if not errors:
        return

    lines: list[str] = []
    for err in errors:
        loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
        lines.append(f"{loc}: {err.message}")
    raise CheckProjectEnvError("schema validation failed:\n" + "\n".join(lines))


def command_registry(contract: dict) -> dict[str, dict]:
    registry: dict[str, dict] = {}
    for command in contract.get("commandRegistry", []):
        command_id = command.get("id")
        if isinstance(command_id, str):
            registry[command_id] = command
    return registry


def validate_contract_semantics(contract: dict) -> None:
    errors: list[str] = []

    command_ids: set[str] = set()
    for command in contract.get("commandRegistry", []):
        command_id = command.get("id")
        if not isinstance(command_id, str):
            continue
        if command_id in command_ids:
            errors.append(f"duplicate commandRegistry id: {command_id}")
        command_ids.add(command_id)

    check_ids: set[str] = set()
    for check in contract.get("environmentChecks", []):
        check_id = check.get("id")
        if isinstance(check_id, str):
            if check_id in check_ids:
                errors.append(f"duplicate environmentChecks id: {check_id}")
            check_ids.add(check_id)

        command_ref = check.get("commandRef")
        if isinstance(command_ref, str) and command_ref not in command_ids:
            label = check_id if isinstance(check_id, str) else "<missing-id>"
            errors.append(f"{label}: unknown commandRef: {command_ref}")

    if errors:
        raise CheckProjectEnvError("contract semantic validation failed:\n" + "\n".join(errors))


def run_command_check(root: Path, command: dict) -> tuple[bool, str]:
    command_args = command.get("command", [])
    if not isinstance(command_args, list) or not command_args:
        return False, "registered command has no command array"

    cwd = root / command.get("cwd", ".")
    timeout = command.get("timeoutSeconds", 120)
    try:
        proc = subprocess.run(
            [str(part) for part in command_args],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return False, f"command not found: {exc.filename}"
    except subprocess.TimeoutExpired:
        return False, f"command timed out after {timeout}s"
    except OSError as exc:
        return False, str(exc)

    if proc.returncode == 0:
        return True, "command exited 0"
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if output:
        return False, f"command exited {proc.returncode}: {output}"
    return False, f"command exited {proc.returncode}"


def run_probe_check(root: Path, probe: dict) -> tuple[bool, str]:
    probe_type = probe.get("type")
    if probe_type == "path_exists":
        path = root / probe.get("path", "")
        return path.exists(), f"path exists: {probe.get('path')}"
    if probe_type == "executable":
        name = probe.get("name", "")
        return shutil.which(name) is not None, f"executable found: {name}"
    return False, f"unknown probe type: {probe_type}"


def evaluate_check(root: Path, check: dict, registry: dict[str, dict]) -> tuple[bool, str]:
    command_ref = check.get("commandRef")
    if isinstance(command_ref, str):
        command = registry.get(command_ref)
        if command is None:
            return False, f"unknown commandRef: {command_ref}"
        return run_command_check(root, command)

    probe = check.get("probe")
    if isinstance(probe, dict):
        return run_probe_check(root, probe)

    return False, "check has neither commandRef nor probe"


def run_checks(root: Path, contract: dict) -> int:
    registry = command_registry(contract)
    blocking_failed = False

    for check in contract.get("environmentChecks", []):
        ok, message = evaluate_check(root, check, registry)
        status = "PASS" if ok else "FAIL"
        severity = check.get("severity", "blocking")
        check_id = check.get("id", "<missing-id>")
        evidence = check.get("evidenceSource", "<missing-evidence>")
        print(f"{status} {severity} {check_id} evidence={evidence} - {message}")
        if not ok and severity == "blocking":
            blocking_failed = True

    return 1 if blocking_failed else 0


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "project-contracts.schema.json"


def default_contract_path(root: Path) -> Path:
    return root / ".harness" / "contracts" / "project-contracts.json"


def run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    contract_path = args.contract or default_contract_path(root)
    schema_path = args.schema

    if not contract_path.exists():
        print(f"NOT_CONFIGURED project environment contract missing: {contract_path}")
        return 3

    try:
        contract = load_json(contract_path)
    except CheckProjectEnvError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        schema = load_json(schema_path)
        if not isinstance(schema, dict):
            raise CheckProjectEnvError(f"{schema_path} top-level JSON must be an object")
    except CheckProjectEnvError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        if not isinstance(contract, dict):
            raise CheckProjectEnvError(f"{contract_path} top-level JSON must be an object")
        validate_contract(contract, schema)
        validate_contract_semantics(contract)
    except CheckProjectEnvError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return run_checks(root, contract)


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Validate and execute project environment contracts")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument(
        "--contract",
        type=Path,
        help="Project contract JSON; defaults to .harness/contracts/project-contracts.json under --root",
    )
    parser.add_argument("--schema", type=Path, default=default_schema_path(), help="Project contracts schema")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
