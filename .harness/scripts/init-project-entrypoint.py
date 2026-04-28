#!/usr/bin/env python3
"""
init-project-entrypoint.py

Detect or update Harness project entrypoints. The script is deterministic:
it only creates or replaces the harness-engineering managed block and writes
the project-entrypoints contract.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: 需要 jsonschema>=4.18，请执行 `pip install jsonschema`", file=sys.stderr)
    sys.exit(2)


START_MARKER = "<!-- harness-engineering:start -->"
END_MARKER = "<!-- harness-engineering:end -->"
MANAGED_BLOCK_VERSION = "harness-entrypoint-block-v1"
PROJECT_ARCHITECTURE_REF = "ARCHITECTURE.md"
HARNESS_ARCHITECTURE_REF = ".harness/ARCHITECTURE.md"

ENTRYPOINT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("AGENTS.md", "generic-agent"),
    ("CLAUDE.md", "tool-agent"),
    ("GEMINI.md", "tool-agent"),
    (".github/copilot-instructions.md", "tool-agent"),
    (".cursor/rules/*.mdc", "editor-rule"),
    (".cursorrules", "editor-rule"),
    (".windsurfrules", "editor-rule"),
    (".windsurf/rules/*.md", "editor-rule"),
    (".clinerules", "editor-rule"),
    (".roo/rules/*.md", "editor-rule"),
)


class InitEntrypointError(Exception):
    pass


def default_schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "project-entrypoints.schema.json"


def default_contract_path(root: Path) -> Path:
    return root / ".harness" / "contracts" / "project-entrypoints.json"


def has_harness_block(text: str) -> bool:
    return START_MARKER in text and END_MARKER in text


def harness_block_version(text: str) -> str | None:
    if not has_harness_block(text):
        return None
    if f"Managed block version: `{MANAGED_BLOCK_VERSION}`" in text:
        return MANAGED_BLOCK_VERSION
    return "legacy"


def relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def detect_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern, kind in ENTRYPOINT_PATTERNS:
        matches = sorted(root.glob(pattern))
        for path in matches:
            if not path.is_file():
                continue
            relative = relative_posix(root, path)
            if relative in seen:
                continue
            seen.add(relative)
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = ""
            entries.append(
                {
                    "path": relative,
                    "kind": kind,
                    "harnessBlock": "present" if has_harness_block(text) else "absent",
                    "harnessBlockVersion": harness_block_version(text),
                    "evidenceSource": relative,
                }
            )
    return entries


def canonical_entry(entries: list[dict[str, str]], explicit_entry: str | None = None) -> str | None:
    if explicit_entry:
        return explicit_entry
    for entry in entries:
        if entry["path"] == "AGENTS.md":
            return "AGENTS.md"
    if entries:
        return entries[0]["path"]
    return None


def contract_for(root: Path, explicit_entry: str | None = None) -> dict[str, Any]:
    entries = detect_entries(root)
    canonical = canonical_entry(entries, explicit_entry)
    return {
        "$schema": "../schemas/project-entrypoints.schema.json",
        "contractVersion": "project-entrypoints-v1",
        "managedBlockVersion": MANAGED_BLOCK_VERSION,
        "canonicalEntry": canonical or "",
        "projectArchitectureRef": PROJECT_ARCHITECTURE_REF,
        "harnessArchitectureRef": HARNESS_ARCHITECTURE_REF,
        "detectedEntries": entries,
    }


def load_schema(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InitEntrypointError(f"schema not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InitEntrypointError(f"schema JSON parse failed {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InitEntrypointError(f"{path} top-level JSON must be an object")
    return data


def validate_contract(contract: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(contract), key=lambda err: list(err.absolute_path))
    if not errors:
        return
    lines: list[str] = []
    for err in errors:
        loc = "/".join(str(part) for part in err.absolute_path) or "<root>"
        lines.append(f"{loc}: {err.message}")
    raise InitEntrypointError("schema validation failed:\n" + "\n".join(lines))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def managed_block() -> str:
    return (
        f"{START_MARKER}\n"
        "## Harness Engineering\n\n"
        "This repository uses Harness Engineering for agent workflow control.\n\n"
        f"Managed block version: `{MANAGED_BLOCK_VERSION}`\n\n"
        "Read order:\n"
        "1. This agent entry document.\n"
        "2. Project business architecture: `ARCHITECTURE.md`.\n"
        "3. Harness framework architecture: `.harness/ARCHITECTURE.md`.\n"
        "4. Harness lifecycle rules: `.harness/rules/workflow-lifecycle.md`.\n"
        "5. Scenario rules: `.harness/rules/session-start.md`, `.harness/rules/handoff-rules.md`, `.harness/rules/archive-rules.md`, and `.harness/rules/backlog-rules.md`.\n"
        "6. Harness project contracts: `.harness/contracts/`.\n\n"
        "Conflict priority:\n"
        "- Target project rules remain valid when compatible with Harness lifecycle.\n"
        "- Workflow, task, testing, review, state, commit, handoff, backlog, or archive conflicts map to Harness lifecycle.\n"
        "- Report conflicts before changing user-owned prose outside this managed block.\n\n"
        "Workflow mapping:\n"
        "- startup and resume rules map to `session-start.py`.\n"
        "- planning maps to `planning`.\n"
        "- development maps to `implementing`.\n"
        "- tests map to the `testing` gate.\n"
        "- reviews map to the `reviewing` gate.\n"
        "- task completion commits map to `commit-task.py`.\n"
        "- L0/L1 completion maps to `complete-workflow.py`.\n"
        "- L2/L3 archive maps to `archive-plan.py`.\n"
        "- incoming work maps to `backlog-intake.py`.\n\n"
        "Truth sources:\n"
        "- Workflow runtime: `work/workflow-state.json`\n"
        "- Task runtime: `work/plans/active/<PLAN-ID>/tasks.json`\n"
        "- Planning contract: `work/plans/active/<PLAN-ID>/plan.md`\n"
        "- Recovery summary: `work/plans/active/<PLAN-ID>/handoff.md`\n"
        "- Project environment contract: `.harness/contracts/project-contracts.json`\n"
        "- Project entrypoint contract: `.harness/contracts/project-entrypoints.json`\n\n"
        "Write gateways:\n"
        "- `workflow-state.json` is written only through `state-write.py` or lifecycle tools that call it.\n"
        "- `tasks.json` is initialized through `materialize-tasks.py` and updated through `update-task.py`.\n"
        "- Phase transitions use `lifecycle-transaction.py` when available.\n"
        "- Backlog writes use `backlog-intake.py`.\n\n"
        "Task modeling:\n"
        "- A task is a deliverable work unit.\n"
        "- Testing, review, architecture impact, commit, and handoff are gates or audit actions, not tasks.\n"
        "- L0/L1 do not create plans.\n"
        "- L2/L3 use one active plan and one active task during implementing/testing/reviewing.\n"
        f"{END_MARKER}"
    )


def replace_managed_block(text: str) -> str:
    block = managed_block()
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        flags=re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    stripped = text.rstrip()
    if stripped:
        return stripped + "\n\n" + block + "\n"
    return block + "\n"


def ensure_project_architecture(root: Path) -> None:
    path = root / PROJECT_ARCHITECTURE_REF
    if path.exists():
        return
    atomic_write_text(path, "")


def write_entrypoint(root: Path, entry: str, *, create: bool) -> dict[str, Any]:
    path = root / entry
    if create:
        if path.exists():
            raise InitEntrypointError(f"entrypoint already exists: {entry}")
        text = ""
    else:
        if not path.exists():
            raise InitEntrypointError(f"entrypoint not found: {entry}")
        text = path.read_text(encoding="utf-8")

    atomic_write_text(path, replace_managed_block(text))
    ensure_project_architecture(root)

    contract = contract_for(root, entry)
    for detected in contract["detectedEntries"]:
        if detected["path"] == entry:
            detected["harnessBlock"] = "present"
            detected["harnessBlockVersion"] = MANAGED_BLOCK_VERSION
    if not any(detected["path"] == entry for detected in contract["detectedEntries"]):
        contract["detectedEntries"].insert(
            0,
            {
                "path": entry,
                "kind": "generic-agent" if entry == "AGENTS.md" else "tool-agent",
                "harnessBlock": "present",
                "harnessBlockVersion": MANAGED_BLOCK_VERSION,
                "evidenceSource": entry,
            },
        )
    return contract


def run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    schema = load_schema(args.schema)

    try:
        if args.detect:
            contract = contract_for(root)
            if not contract["detectedEntries"]:
                print("NEEDS_ENTRYPOINT recommend creating AGENTS.md")
                return 3
            validate_contract(contract, schema)
            print(json.dumps(contract, ensure_ascii=False, indent=2))
            return 0

        if args.create:
            contract = write_entrypoint(root, args.create, create=True)
            action = f"CREATED {args.create}"
        elif args.write:
            contract = write_entrypoint(root, args.entry, create=False)
            action = f"UPDATED {args.entry}"
        else:
            raise InitEntrypointError("one of --detect, --write, or --create is required")

        validate_contract(contract, schema)
        atomic_write_json(args.contract or default_contract_path(root), contract)
        print(action)
        print(json.dumps(contract, ensure_ascii=False, indent=2))
        return 0
    except InitEntrypointError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Detect or update Harness project entrypoints")
    parser.add_argument("--root", type=Path, default=repo_root, help="Repository root")
    parser.add_argument("--schema", type=Path, default=default_schema_path(), help="Project entrypoints schema")
    parser.add_argument("--contract", type=Path, help="Output contract path")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--detect", action="store_true", help="Detect entrypoint candidates and print contract JSON")
    mode.add_argument("--write", action="store_true", help="Update an existing entrypoint managed block")
    mode.add_argument("--create", metavar="ENTRY", help="Create a new entrypoint containing the managed block")
    parser.add_argument("--entry", default="AGENTS.md", help="Entrypoint path for --write")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
