#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_TEMPLATE = REPO_ROOT / ".harness" / "templates" / "plan.template.md"
HANDOFF_TEMPLATE = REPO_ROOT / ".harness" / "templates" / "handoff.template.md"
MATERIALIZE = REPO_ROOT / ".harness" / "scripts" / "materialize-tasks.py"
TASKS_SCHEMA = REPO_ROOT / ".harness" / "schemas" / "tasks.schema.json"


class PlanWritingTemplatesTest(unittest.TestCase):
    def test_plan_template_materializes_to_schema_valid_idle_tasks(self) -> None:
        self.assertTrue(PLAN_TEMPLATE.exists(), "plan.template.md must exist")

        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "work" / "plans" / "active" / "PLAN-001"
            plan_dir.mkdir(parents=True)
            plan_path = plan_dir / "plan.md"
            tasks_path = plan_dir / "tasks.json"
            plan_path.write_text(PLAN_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(MATERIALIZE),
                    str(plan_path),
                    "--out",
                    str(tasks_path),
                    "--schema",
                    str(TASKS_SCHEMA),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(tasks_path.read_text(encoding="utf-8"))
            schema = json.loads(TASKS_SCHEMA.read_text(encoding="utf-8"))
            errors = list(Draft202012Validator(schema).iter_errors(data))
            self.assertEqual(errors, [])
            self.assertEqual(data["planId"], "PLAN-001")
            self.assertTrue(data["tasks"])
            for task in data["tasks"]:
                self.assertEqual(task["status"], "idle")
                self.assertEqual(task["ownerRole"], "developer")
                self.assertEqual(task["verification"]["lastResult"], "not_run")
                self.assertNotIn("review", task)

    def test_handoff_template_describes_pre_activation_planning_state(self) -> None:
        text = HANDOFF_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("activeTaskId: null", text)
        self.assertIn("currentPhase: planning", text)
        self.assertIn("ownerRole: planner", text)
        self.assertIn("taskStatus: all tasks idle", text)
        self.assertNotIn("activeTaskId: TASK-001", text)
        self.assertNotIn("currentPhase: implementing", text)
        self.assertNotIn("taskStatus: implementing", text)


if __name__ == "__main__":
    unittest.main()
