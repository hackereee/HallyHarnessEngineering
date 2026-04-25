#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "materialize-tasks.py"
SCHEMA = REPO_ROOT / ".harness" / "schemas" / "tasks.schema.json"


PLAN_TEXT = """# Sample Plan

<a id="task-001-define-schema"></a>

### TASK-001: Define schema

Goal: Define the schema contract.

Files:
- Create: `.harness/schemas/tasks.schema.json`
- Modify: `.harness/templates/tasks.template.json`
- Test: `.harness/scripts/test_materialize_tasks.py`

Depends on: []

Acceptance:
- Schema validates the generated tasks manifest.
- Task contract anchors are stable.

Verification:
- Run: `python3 -m json.tool work/plans/active/PLAN-123/tasks.json`
- Check: generated task status remains idle.

<a id="task-002-wire-validation"></a>

### TASK-002: Wire validation

Goal: Validate task dependencies.

Files:
- Modify: `.harness/scripts/materialize-tasks.py`

Depends on: [TASK-001]

Acceptance:
- DependsOn references existing task IDs.

Verification:
- Check: dependency validation rejects unknown task IDs.
"""


class MaterializeTasksTest(unittest.TestCase):
    def run_script(self, plan_path: Path, out_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(plan_path),
                "--out",
                str(out_path),
                "--schema",
                str(SCHEMA),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_materializes_plan_contracts_to_schema_valid_tasks_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "work" / "plans" / "active" / "PLAN-123"
            plan_dir.mkdir(parents=True)
            plan_path = plan_dir / "plan.md"
            out_path = plan_dir / "tasks.json"
            plan_path.write_text(PLAN_TEXT, encoding="utf-8")

            result = self.run_script(plan_path, out_path)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(out_path.read_text(encoding="utf-8"))
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
            errors = list(Draft202012Validator(schema).iter_errors(data))
            self.assertEqual(errors, [])
            self.assertEqual(data["planId"], "PLAN-123")
            self.assertEqual(data["planRef"], "./plan.md")
            self.assertEqual(
                data["$schema"],
                os.path.relpath(SCHEMA.resolve(), out_path.parent.resolve()),
            )
            self.assertEqual([task["taskId"] for task in data["tasks"]], ["TASK-001", "TASK-002"])
            self.assertEqual(data["tasks"][0]["status"], "idle")
            self.assertEqual(data["tasks"][0]["currentStep"], "")
            self.assertEqual(data["tasks"][0]["nextAction"], "")
            self.assertEqual(data["tasks"][0]["verification"]["lastResult"], "not_run")
            self.assertNotIn("review", data["tasks"][0])
            self.assertEqual(data["tasks"][1]["dependsOn"], ["TASK-001"])
            self.assertEqual(data["tasks"][0]["files"]["create"], [".harness/schemas/tasks.schema.json"])
            self.assertEqual(data["tasks"][0]["files"]["modify"], [".harness/templates/tasks.template.json"])
            self.assertEqual(data["tasks"][0]["files"]["test"], [".harness/scripts/test_materialize_tasks.py"])
            self.assertEqual(
                data["tasks"][0]["verification"]["commands"],
                ["python3 -m json.tool work/plans/active/PLAN-123/tasks.json"],
            )
            self.assertEqual(
                data["tasks"][0]["verification"]["checks"],
                ["generated task status remains idle."],
            )

    def test_rejects_unknown_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "work" / "plans" / "active" / "PLAN-123"
            plan_dir.mkdir(parents=True)
            plan_path = plan_dir / "plan.md"
            out_path = plan_dir / "tasks.json"
            plan_path.write_text(PLAN_TEXT.replace("[TASK-001]", "[TASK-999]"), encoding="utf-8")

            result = self.run_script(plan_path, out_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown dependsOn", result.stderr)
            self.assertFalse(out_path.exists())


if __name__ == "__main__":
    unittest.main()
