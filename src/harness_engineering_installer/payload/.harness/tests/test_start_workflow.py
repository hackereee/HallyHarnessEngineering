#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "start-workflow.py"


def archived_state() -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-plan-001-v1",
        "activePlanRef": None,
        "activeTaskId": None,
        "workflowStatus": "archived",
        "currentPhase": "archiving",
        "ownerRole": "developer",
        "nextAction": "开启下一个 workflow",
        "updatedAt": "2026-04-27T09:00:00+08:00",
    }


def active_direct_state() -> dict:
    state = archived_state()
    state.update(
        {
            "workflowId": "workflow-fix-current-20260427-v1",
            "workflowStatus": "active",
            "currentPhase": "implementing",
            "nextAction": "运行当前 workflow 验证",
        }
    )
    return state


def task_fixture() -> dict:
    return {
        "taskId": "TASK-001",
        "title": "Implement planned workflow",
        "planSection": "task-001-implement-planned-workflow",
        "status": "idle",
        "currentStep": "",
        "nextAction": "",
        "ownerRole": "developer",
        "dependsOn": [],
        "files": {"create": [], "modify": ["src/example.py"], "test": []},
        "acceptance": ["Planned workflow is implemented"],
        "verification": {
            "commands": ["python3 .harness/tests/test_start_workflow.py"],
            "checks": [],
            "lastResult": "not_run",
        },
        "review": {
            "score": 0,
            "threshold": 85,
            "lastResult": "not_run",
            "rubricVersion": "review-rubric-v1",
            "checks": [],
            "findings": [],
            "reportRef": "",
        },
        "blockedReason": "",
    }


def valid_handoff() -> str:
    return (
        "# Handoff\n\n"
        "- workflowId: workflow-plan-002-v1\n"
        "- planRef: ./plans/active/PLAN-002/plan.md\n"
        "- activeTaskId: null\n"
        "- currentPhase: planning\n"
        "- taskStatus: all tasks idle\n"
        "- ownerRole: planner\n"
        "- sourceSessionId: session-test\n"
        "\n"
        "## Current Status\n\n"
        "The active plan package exists before workflow start.\n"
        "\n"
        "## Role Handoff\n\n"
        "- fromRole: planner\n"
        "- toRole: developer\n"
        "- reason: plan package is ready for workflow start\n"
        "- stateSource: workflow-state.json and tasks.json\n"
        "\n"
        "## Risks\n\n"
        "- start-workflow.py must bind the plan without activating a task.\n"
        "\n"
        "## Next Action\n\n"
        "Activate the first eligible idle task.\n"
    )


class StartWorkflowTest(unittest.TestCase):
    def write_harness_assets(self, root: Path) -> None:
        for relative in (
            ".harness/schemas/workflow-state.schema.json",
            ".harness/schemas/tasks.schema.json",
            ".harness/scripts/lint-harness.py",
            ".harness/scripts/validate-state.py",
            ".harness/scripts/state-write.py",
            ".harness/scripts/start-workflow.py",
        ):
            source = REPO_ROOT / relative
            if not source.exists():
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def write_state(self, root: Path, state: dict) -> Path:
        state_path = root / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return state_path

    def write_active_plan(self, root: Path) -> None:
        plan_dir = root / "work" / "plans" / "active" / "PLAN-002"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            "# PLAN-002: Planned workflow\n\n"
            "## Plan Review Gate\n\n"
            "Status: passed\n\n"
            '<a id="task-001-implement-planned-workflow"></a>\n\n'
            "### TASK-001: Implement planned workflow\n",
            encoding="utf-8",
        )
        (plan_dir / "handoff.md").write_text(valid_handoff(), encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-002",
                    "planRef": "./plan.md",
                    "tasks": [task_fixture()],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def run_start(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                *args,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_starts_new_direct_workflow_from_archived_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = self.write_state(root, archived_state())

            result = self.run_start(
                root,
                "--level",
                "L1",
                "--workflow-id",
                "workflow-fix-next-20260427-v1",
                "--next-action",
                "判断当前需求的任务等级",
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["workflowId"], "workflow-fix-next-20260427-v1")
            self.assertEqual(state["workflowStatus"], "active")
            self.assertEqual(state["currentPhase"], "implementing")
            self.assertEqual(state["ownerRole"], "developer")
            self.assertIsNone(state["activePlanRef"])
            self.assertIsNone(state["activeTaskId"])

    def test_rejects_start_when_current_workflow_is_not_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = self.write_state(root, active_direct_state())
            before = state_path.read_text(encoding="utf-8")

            result = self.run_start(
                root,
                "--level",
                "L1",
                "--workflow-id",
                "workflow-fix-next-20260427-v1",
                "--next-action",
                "判断当前需求的任务等级",
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("终态", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_starts_planned_workflow_when_active_plan_package_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = self.write_state(root, archived_state())
            self.write_active_plan(root)

            result = self.run_start(
                root,
                "--level",
                "L2",
                "--workflow-id",
                "workflow-plan-002-v1",
                "--plan-ref",
                "./plans/active/PLAN-002/plan.md",
                "--next-action",
                "激活 PLAN-002 首个任务",
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["workflowId"], "workflow-plan-002-v1")
            self.assertEqual(state["workflowStatus"], "active")
            self.assertEqual(state["currentPhase"], "planning")
            self.assertEqual(state["ownerRole"], "planner")
            self.assertEqual(state["activePlanRef"], "./plans/active/PLAN-002/plan.md")
            self.assertIsNone(state["activeTaskId"])

    def test_rejects_planned_workflow_when_plan_review_gate_is_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = self.write_state(root, archived_state())
            self.write_active_plan(root)
            plan_path = root / "work" / "plans" / "active" / "PLAN-002" / "plan.md"
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8").replace("Status: passed", "Status: failed"),
                encoding="utf-8",
            )
            before = state_path.read_text(encoding="utf-8")

            result = self.run_start(
                root,
                "--level",
                "L2",
                "--workflow-id",
                "workflow-plan-002-v1",
                "--plan-ref",
                "./plans/active/PLAN-002/plan.md",
                "--next-action",
                "激活 PLAN-002 首个任务",
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("Plan Review Gate", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
