#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "session-start.py"


def base_task() -> dict:
    return {
        "taskId": "TASK-001",
        "title": "Implement feature",
        "planSection": "task-001-implement-feature",
        "status": "idle",
        "currentStep": "",
        "nextAction": "",
        "ownerRole": "developer",
        "dependsOn": [],
        "files": {"create": [], "modify": ["src/example.py"], "test": []},
        "acceptance": ["Feature is implemented"],
        "verification": {
            "commands": [],
            "checks": ["Manual check passes"],
            "lastResult": "not_run",
        },
        "blockedReason": "",
    }


def direct_state() -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-fix-login-20260425-v1",
        "activePlanRef": None,
        "activeTaskId": None,
        "workflowStatus": "active",
        "currentPhase": "implementing",
        "ownerRole": "developer",
        "nextAction": "Run targeted login regression test",
        "updatedAt": "2026-04-25T20:00:00+08:00",
    }


class SessionStartTest(unittest.TestCase):
    def write_harness_assets(self, root: Path) -> None:
        for relative in (
            ".harness/schemas/workflow-state.schema.json",
            ".harness/schemas/tasks.schema.json",
            ".harness/templates/workflow-state.template.json",
            ".harness/templates/plan.template.md",
            ".harness/templates/tasks.template.json",
            ".harness/templates/handoff.template.md",
            ".harness/rules/workflow-lifecycle.md",
            ".harness/scripts/lint-harness.py",
            ".harness/scripts/validate-state.py",
            ".harness/scripts/state-write.py",
            ".harness/scripts/update-task.py",
            ".harness/scripts/select-next-task.py",
            ".harness/scripts/materialize-tasks.py",
            ".harness/scripts/lifecycle-transaction.py",
            ".harness/scripts/session-start.py",
        ):
            source = REPO_ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def run_session_start(
        self,
        root: Path,
        *,
        session_id: str = "test-001",
        timestamp: str = "2026-04-27T09:00:00+08:00",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                "--session-id",
                session_id,
                "--timestamp",
                timestamp,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def write_active_plan_without_state(self, root: Path) -> None:
        plan_dir = root / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            '# Plan\n\n<a id="task-001-implement-feature"></a>\n\n'
            "### TASK-001: Implement feature\n",
            encoding="utf-8",
        )
        (plan_dir / "handoff.md").write_text("# Handoff\n", encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-001",
                    "planRef": "./plan.md",
                    "tasks": [base_task()],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_bootstraps_missing_workflow_state_and_writes_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            state_path = root / "work" / "workflow-state.json"
            self.assertTrue(state_path.exists())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["$schema"], "../.harness/schemas/workflow-state.schema.json")
            self.assertEqual(state["workflowId"], "workflow-adhoc-20260427-001")
            self.assertEqual(state["activePlanRef"], None)
            self.assertEqual(state["activeTaskId"], None)
            self.assertEqual(state["updatedAt"], "2026-04-27T09:00:00+08:00")
            self.assertEqual(state["nextAction"], "判断当前需求的任务等级")

            session_path = root / "work" / "sessions" / "2026-04-27" / "session-test-001.md"
            self.assertTrue(session_path.exists())
            session_text = session_path.read_text(encoding="utf-8")
            self.assertIn("Harness lint: passed", session_text)
            self.assertIn("Workflow state validation: passed", session_text)
            self.assertIn("Previous session: none", session_text)
            self.assertIn("workflowId: workflow-adhoc-20260427-001", session_text)
            self.assertIn("nextAction: 判断当前需求的任务等级", session_text)
            self.assertIn("NEXT_ACTION=判断当前需求的任务等级", result.stdout)

    def test_existing_workflow_state_is_validated_but_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = root / "work" / "workflow-state.json"
            state_path.parent.mkdir(parents=True)
            original_text = json.dumps(direct_state(), ensure_ascii=False, indent=2) + "\n"
            state_path.write_text(original_text, encoding="utf-8")

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_text)
            session_path = root / "work" / "sessions" / "2026-04-27" / "session-test-001.md"
            self.assertIn(
                "nextAction: Run targeted login regression test",
                session_path.read_text(encoding="utf-8"),
            )

    def test_missing_state_with_active_plan_is_blocked_without_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            self.write_active_plan_without_state(root)

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("workflow-state.json 不存在但存在 active plan", result.stdout + result.stderr)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_references_previous_session_without_parsing_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            first = self.run_session_start(
                root,
                session_id="previous",
                timestamp="2026-04-26T20:00:00+08:00",
            )
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)

            second = self.run_session_start(root)

            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            session_path = root / "work" / "sessions" / "2026-04-27" / "session-test-001.md"
            session_text = session_path.read_text(encoding="utf-8")
            self.assertIn(
                "Previous session: work/sessions/2026-04-26/session-previous.md",
                session_text,
            )


if __name__ == "__main__":
    unittest.main()
