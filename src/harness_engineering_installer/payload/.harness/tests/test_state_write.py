#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_WRITE = REPO_ROOT / ".harness" / "scripts" / "state-write.py"
VALIDATOR = REPO_ROOT / ".harness" / "scripts" / "validate-state.py"
STATE_SCHEMA = REPO_ROOT / ".harness" / "schemas" / "workflow-state.schema.json"


def base_state() -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-fix-login-20260425-v1",
        "activePlanRef": None,
        "activeTaskId": None,
        "workflowStatus": "active",
        "currentPhase": "implementing",
        "ownerRole": "developer",
        "nextAction": "Run login regression test",
        "updatedAt": "2026-04-25T20:00:00+08:00",
    }


def archived_state() -> dict:
    state = base_state()
    state.update(
        {
            "workflowId": "workflow-plan-001-v1",
            "workflowStatus": "archived",
            "currentPhase": "archiving",
            "ownerRole": "developer",
            "nextAction": "Start next workflow",
        }
    )
    return state


def direct_reviewing_state() -> dict:
    state = base_state()
    state.update(
        {
            "currentPhase": "reviewing",
            "ownerRole": "reviewer",
            "nextAction": "Review direct workflow evidence",
        }
    )
    return state


def archiving_plan_state() -> dict:
    state = base_state()
    state.update(
        {
            "workflowId": "workflow-plan-001-v1",
            "activePlanRef": "./plans/active/PLAN-001/plan.md",
            "activeTaskId": None,
            "currentPhase": "archiving",
            "ownerRole": "developer",
            "nextAction": "Archive current plan package",
        }
    )
    return state


def plan_state() -> dict:
    state = base_state()
    state.update(
        {
            "workflowId": "workflow-plan-001-v1",
            "activePlanRef": "./plans/active/PLAN-001/plan.md",
            "activeTaskId": "TASK-001",
            "currentPhase": "reviewing",
            "ownerRole": "reviewer",
            "nextAction": "Review TASK-001 delivery",
        }
    )
    return state


def review_fixture(last_result: str = "not_run") -> dict:
    return {
        "score": 90 if last_result == "passed" else 0,
        "threshold": 85,
        "lastResult": last_result,
        "rubricVersion": "review-rubric-v1",
        "checks": ["review gate passed"] if last_result == "passed" else [],
        "findings": [],
        "reportRef": "work/sessions/2026-04-27/session-review.md" if last_result != "not_run" else "",
    }


def task_fixture(status: str = "reviewing", review_result: str = "not_run") -> dict:
    owner_by_status = {
        "idle": "developer",
        "implementing": "developer",
        "testing": "tester",
        "reviewing": "reviewer",
        "done": "developer",
    }
    return {
        "taskId": "TASK-001",
        "title": "Implement plan workflow",
        "planSection": "task-001-implement-plan-workflow",
        "status": status,
        "currentStep": "",
        "nextAction": "",
        "ownerRole": owner_by_status[status],
        "dependsOn": [],
        "files": {"create": [], "modify": ["src/workflow.py"], "test": []},
        "acceptance": ["Plan workflow is implemented"],
        "verification": {
            "commands": ["python3 .harness/tests/test_state_write.py"],
            "checks": [],
            "lastResult": "passed" if status in {"reviewing", "done"} else "not_run",
        },
        "review": review_fixture(review_result),
        "blockedReason": "",
    }


class StateWriteTest(unittest.TestCase):
    def write_state(self, tmp: str) -> Path:
        state_path = Path(tmp) / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(base_state(), indent=2) + "\n", encoding="utf-8")
        return state_path

    def write_archived_state(self, tmp: str) -> Path:
        state_path = Path(tmp) / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(archived_state(), indent=2) + "\n", encoding="utf-8")
        return state_path

    def write_archived_state_with_plan(self, tmp: str, *, plan_review_passed: bool = True) -> Path:
        root = Path(tmp)
        plan_dir = root / "work" / "plans" / "active" / "PLAN-002"
        plan_dir.mkdir(parents=True)
        gate_status = "passed" if plan_review_passed else "failed"
        (plan_dir / "plan.md").write_text(
            "# PLAN-002: Planned workflow\n\n"
            "## Plan Review Gate\n\n"
            f"Status: {gate_status}\n\n"
            '<a id="task-001-implement-plan-workflow"></a>\n\n'
            "### TASK-001: Implement plan workflow\n",
            encoding="utf-8",
        )
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-002",
                    "planRef": "./plan.md",
                    "tasks": [task_fixture(status="idle")],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return self.write_archived_state(tmp)

    def write_direct_reviewing_state(self, tmp: str) -> Path:
        state_path = Path(tmp) / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(direct_reviewing_state(), indent=2) + "\n", encoding="utf-8")
        return state_path

    def write_archiving_plan_state_with_active_dir(self, tmp: str) -> Path:
        root = Path(tmp)
        plan_dir = root / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text("# PLAN-001\n", encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-001",
                    "planRef": "./plan.md",
                    "tasks": [task_fixture(status="done", review_result="passed")],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        state_path = root / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(archiving_plan_state(), indent=2) + "\n", encoding="utf-8")
        return state_path

    def write_plan_state(self, tmp: str, task: dict | None = None) -> Path:
        root = Path(tmp)
        plan_dir = root / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text("# PLAN-001\n", encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-001",
                    "planRef": "./plan.md",
                    "tasks": [task or task_fixture()],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        state_path = root / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(plan_state(), indent=2) + "\n", encoding="utf-8")
        return state_path

    def run_state_write(
        self,
        state_path: Path,
        patch: list[dict],
        extra_args: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(STATE_WRITE),
                "--state",
                str(state_path),
                "--schema",
                str(STATE_SCHEMA),
                "--validator",
                str(VALIDATOR),
                "--patch-json",
                json.dumps(patch),
                "--source",
                "test_state_write.py",
                "--reason",
                "verify phase ownerRole warning",
                *(extra_args or []),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_phase_change_without_owner_role_patch_is_rejected_by_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_state(tmp)
            patch = [
                {"op": "replace", "path": "/currentPhase", "value": "testing"},
                {"op": "replace", "path": "/nextAction", "value": "Run verification command"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("'tester' was expected", result.stderr + result.stdout)

            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["currentPhase"], "implementing")

    def test_phase_change_with_owner_role_patch_does_not_warn_about_owner_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_state(tmp)
            patch = [
                {"op": "replace", "path": "/currentPhase", "value": "testing"},
                {"op": "replace", "path": "/ownerRole", "value": "tester"},
                {"op": "replace", "path": "/nextAction", "value": "Run verification command"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertNotIn("ownerRole was not explicitly refreshed", result.stderr)

    def test_rejects_illegal_phase_jump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_state(tmp)
            patch = [
                {"op": "replace", "path": "/currentPhase", "value": "reviewing"},
                {"op": "replace", "path": "/ownerRole", "value": "reviewer"},
                {"op": "replace", "path": "/nextAction", "value": "Review implementation"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("Illegal phase transition", result.stderr + result.stdout)

            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["currentPhase"], "implementing")

    def test_rejects_reviewing_to_archiving_when_active_task_is_not_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_plan_state(tmp)
            before = state_path.read_text(encoding="utf-8")
            patch = [
                {"op": "replace", "path": "/currentPhase", "value": "archiving"},
                {"op": "replace", "path": "/ownerRole", "value": "developer"},
                {"op": "replace", "path": "/activeTaskId", "value": None},
                {"op": "replace", "path": "/nextAction", "value": "Archive current plan package"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("reviewing -> archiving", result.stderr + result.stdout)
            self.assertIn("TASK-001", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_allows_reviewing_to_archiving_when_plan_tasks_are_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_plan_state(tmp, task_fixture(status="done", review_result="passed"))
            patch = [
                {"op": "replace", "path": "/currentPhase", "value": "archiving"},
                {"op": "replace", "path": "/ownerRole", "value": "developer"},
                {"op": "replace", "path": "/activeTaskId", "value": None},
                {"op": "replace", "path": "/nextAction", "value": "Archive current plan package"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["currentPhase"], "archiving")
            self.assertIsNone(data["activeTaskId"])

    def test_rejects_terminal_close_without_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_direct_reviewing_state(tmp)
            before = state_path.read_text(encoding="utf-8")
            patch = [
                {"op": "replace", "path": "/workflowStatus", "value": "completed"},
                {"op": "replace", "path": "/activePlanRef", "value": None},
                {"op": "replace", "path": "/activeTaskId", "value": None},
                {"op": "replace", "path": "/nextAction", "value": "Start next workflow"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("terminal close", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_rejects_archived_close_when_active_plan_dir_remains(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_archiving_plan_state_with_active_dir(tmp)
            before = state_path.read_text(encoding="utf-8")
            patch = [
                {"op": "replace", "path": "/workflowStatus", "value": "archived"},
                {"op": "replace", "path": "/activePlanRef", "value": None},
                {"op": "replace", "path": "/activeTaskId", "value": None},
                {"op": "replace", "path": "/nextAction", "value": "Start next workflow"},
            ]

            result = self.run_state_write(state_path, patch, ["--allow-terminal-close"])

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("active plan", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_terminal_reset_requires_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_archived_state(tmp)
            patch = [
                {"op": "replace", "path": "/workflowId", "value": "workflow-fix-next-20260427-v1"},
                {"op": "replace", "path": "/workflowStatus", "value": "active"},
                {"op": "replace", "path": "/currentPhase", "value": "implementing"},
                {"op": "replace", "path": "/ownerRole", "value": "developer"},
                {"op": "replace", "path": "/activePlanRef", "value": None},
                {"op": "replace", "path": "/activeTaskId", "value": None},
                {"op": "replace", "path": "/nextAction", "value": "Classify the current request task level"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("terminal reset", result.stderr + result.stdout)

    def test_rejects_workflow_id_change_without_terminal_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_archived_state(tmp)
            before = state_path.read_text(encoding="utf-8")
            patch = [
                {"op": "replace", "path": "/workflowId", "value": "workflow-mutated-id-v1"},
                {"op": "replace", "path": "/nextAction", "value": "Start next workflow"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("workflowId", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_planned_terminal_reset_requires_passed_plan_review_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_archived_state_with_plan(tmp, plan_review_passed=False)
            before = state_path.read_text(encoding="utf-8")
            patch = [
                {"op": "replace", "path": "/workflowId", "value": "workflow-plan-002-v1"},
                {"op": "replace", "path": "/workflowStatus", "value": "active"},
                {"op": "replace", "path": "/currentPhase", "value": "planning"},
                {"op": "replace", "path": "/ownerRole", "value": "planner"},
                {"op": "replace", "path": "/activePlanRef", "value": "./plans/active/PLAN-002/plan.md"},
                {"op": "replace", "path": "/activeTaskId", "value": None},
                {"op": "replace", "path": "/nextAction", "value": "Activate PLAN-002 first task"},
            ]

            result = self.run_state_write(state_path, patch, ["--allow-terminal-reset"])

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("Plan Review Gate", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_terminal_status_cannot_be_reopened_with_partial_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_archived_state(tmp)
            before = state_path.read_text(encoding="utf-8")
            patch = [
                {"op": "replace", "path": "/workflowStatus", "value": "active"},
                {"op": "replace", "path": "/nextAction", "value": "Restore old workflow"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("terminal reset", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_allows_terminal_reset_to_new_direct_workflow_with_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_archived_state(tmp)
            patch = [
                {"op": "replace", "path": "/workflowId", "value": "workflow-fix-next-20260427-v1"},
                {"op": "replace", "path": "/workflowStatus", "value": "active"},
                {"op": "replace", "path": "/currentPhase", "value": "implementing"},
                {"op": "replace", "path": "/ownerRole", "value": "developer"},
                {"op": "replace", "path": "/activePlanRef", "value": None},
                {"op": "replace", "path": "/activeTaskId", "value": None},
                {"op": "replace", "path": "/nextAction", "value": "Classify the current request task level"},
            ]

            result = self.run_state_write(state_path, patch, ["--allow-terminal-reset"])

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["workflowId"], "workflow-fix-next-20260427-v1")
            self.assertEqual(data["workflowStatus"], "active")
            self.assertEqual(data["currentPhase"], "implementing")
            self.assertIsNone(data["activePlanRef"])
            self.assertIsNone(data["activeTaskId"])


if __name__ == "__main__":
    unittest.main()
