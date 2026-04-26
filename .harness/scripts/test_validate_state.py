#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / ".harness" / "scripts" / "validate-state.py"
STATE_SCHEMA = REPO_ROOT / ".harness" / "schemas" / "workflow-state.schema.json"


PHASE_OWNER_ROLE = {
    "planning": "planner",
    "implementing": "developer",
    "testing": "tester",
    "reviewing": "reviewer",
    "archiving": "developer",
}


def base_task(status: str, owner_role: str) -> dict:
    return {
        "taskId": "TASK-001",
        "title": "Implement feature",
        "planSection": "task-001-implement-feature",
        "status": status,
        "currentStep": "",
        "nextAction": "",
        "ownerRole": owner_role,
        "dependsOn": [],
        "files": {"create": [], "modify": ["src/example.py"], "test": []},
        "acceptance": ["Feature is implemented"],
        "verification": {
            "commands": [],
            "checks": ["Manual check passes"],
            "lastResult": "passed",
        },
        "blockedReason": "",
    }


class ValidateStateTest(unittest.TestCase):
    def test_default_workflow_state_template_validates(self) -> None:
        template = REPO_ROOT / ".harness" / "templates" / "workflow-state.template.json"

        result = self.run_validator(template)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def write_fixture(
        self,
        tmp: str,
        phase: str,
        task_status: str,
        task_owner_role: str,
        workflow_owner_role: str | None = None,
    ) -> Path:
        root = Path(tmp)
        work = root / "work"
        plan_dir = work / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-001",
                    "planRef": "./plan.md",
                    "tasks": [base_task(task_status, task_owner_role)],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        state_path = work / "workflow-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "$schema": "../.harness/schemas/workflow-state.schema.json",
                    "workflowId": "workflow-plan-001-v1",
                    "activePlanRef": "./plans/active/PLAN-001/plan.md",
                    "activeTaskId": "TASK-001",
                    "workflowStatus": "active",
                    "currentPhase": phase,
                    "ownerRole": workflow_owner_role or PHASE_OWNER_ROLE[phase],
                    "nextAction": "Review implementation",
                    "updatedAt": "2026-04-25T20:00:00+08:00",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return state_path

    def write_direct_fixture(self, tmp: str, phase: str, owner_role: str) -> Path:
        root = Path(tmp)
        work = root / "work"
        work.mkdir(parents=True)
        state_path = work / "workflow-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "$schema": "../.harness/schemas/workflow-state.schema.json",
                    "workflowId": "workflow-fix-login-20260425-v1",
                    "activePlanRef": None,
                    "activeTaskId": None,
                    "workflowStatus": "active",
                    "currentPhase": phase,
                    "ownerRole": owner_role,
                    "nextAction": "Run targeted login regression test",
                    "updatedAt": "2026-04-25T20:00:00+08:00",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return state_path

    def run_validator(self, state_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--state",
                str(state_path),
                "--schema",
                str(STATE_SCHEMA),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_planning_phase_rejects_missing_active_plan_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            work.mkdir(parents=True)
            state_path = work / "workflow-state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "$schema": "../.harness/schemas/workflow-state.schema.json",
                        "workflowId": "workflow-plan-001-v1",
                        "activePlanRef": "./plans/active/PLAN-999/plan.md",
                        "activeTaskId": None,
                        "workflowStatus": "active",
                        "currentPhase": "planning",
                        "ownerRole": "planner",
                        "nextAction": "Materialize plan package",
                        "updatedAt": "2026-04-25T20:00:00+08:00",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_validator(state_path)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("activePlanRef 指向的 plan.md 不存在", result.stdout + result.stderr)

    def test_reviewing_phase_accepts_reviewing_reviewer_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_fixture(tmp, "reviewing", "reviewing", "reviewer")

            result = self.run_validator(state_path)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_reviewing_phase_rejects_testing_tester_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_fixture(tmp, "reviewing", "testing", "tester")

            result = self.run_validator(state_path)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("currentPhase='reviewing'", result.stdout + result.stderr)

    def test_direct_testing_phase_accepts_tester_owner_role_without_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_direct_fixture(tmp, "testing", "tester")

            result = self.run_validator(state_path)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_direct_reviewing_phase_accepts_reviewer_owner_role_without_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_direct_fixture(tmp, "reviewing", "reviewer")

            result = self.run_validator(state_path)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
