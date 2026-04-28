#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "lifecycle-transaction.py"


def review_fixture(last_result: str = "not_run") -> dict:
    score = 90 if last_result == "passed" else 0
    checks = ["review gate passed"] if last_result == "passed" else []
    findings = []
    if last_result == "failed":
        checks = ["review gate failed"]
        findings = [
            {
                "severity": "important",
                "blocking": True,
                "summary": "Lifecycle requirement is not satisfied",
            }
        ]
    return {
        "score": score,
        "threshold": 85,
        "lastResult": last_result,
        "rubricVersion": "review-rubric-v1",
        "checks": checks,
        "findings": findings,
        "reportRef": "work/sessions/2026-04-27/session-review.md" if last_result != "not_run" else "",
    }


def task_fixture(
    task_id: str,
    title: str,
    *,
    status: str = "idle",
    depends_on: list[str] | None = None,
    review_result: str | None = None,
) -> dict:
    slug = task_id.lower()
    owner_by_status = {
        "idle": "developer",
        "implementing": "developer",
        "testing": "tester",
        "reviewing": "reviewer",
        "done": "developer",
    }
    verification_result = "passed" if status in {"reviewing", "done"} else "not_run"
    resolved_review_result = review_result or ("passed" if status == "done" else "not_run")
    return {
        "taskId": task_id,
        "title": title,
        "planSection": f"{slug}-section",
        "status": status,
        "currentStep": "",
        "nextAction": "",
        "ownerRole": owner_by_status[status],
        "dependsOn": depends_on or [],
        "files": {"create": [], "modify": [f"src/{slug}.py"], "test": []},
        "acceptance": [f"{task_id} acceptance is met"],
        "verification": {
            "commands": ["python3 -m unittest discover -s .harness/tests -p 'test_*.py'"],
            "checks": [],
            "lastResult": verification_result,
        },
        "review": review_fixture(resolved_review_result),
        "blockedReason": "",
    }


def workflow_state(
    phase: str,
    owner_role: str,
    active_task_id: str | None,
    *,
    workflow_status: str = "active",
) -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-plan-001-v1",
        "activePlanRef": "./plans/active/PLAN-001/plan.md",
        "activeTaskId": active_task_id,
        "workflowStatus": workflow_status,
        "currentPhase": phase,
        "ownerRole": owner_role,
        "nextAction": "执行 lifecycle transaction",
        "updatedAt": "2026-04-27T09:00:00+08:00",
    }


def valid_handoff() -> str:
    return (
        "# Handoff\n\n"
        "- workflowId: workflow-plan-001-v1\n"
        "- planRef: ./plans/active/PLAN-001/plan.md\n"
        "- activeTaskId: null\n"
        "- currentPhase: planning\n"
        "- taskStatus: all tasks idle\n"
        "- ownerRole: planner\n"
        "- sourceSessionId: session-test\n"
        "\n"
        "## Current Status\n\n"
        "The plan package is ready for lifecycle transaction testing.\n"
        "\n"
        "## Role Handoff\n\n"
        "- fromRole: planner\n"
        "- toRole: developer\n"
        "- reason: plan package is ready for activation\n"
        "- stateSource: workflow-state.json and tasks.json\n"
        "\n"
        "## Risks\n\n"
        "- Keep task and state writes behind lifecycle gateways.\n"
        "\n"
        "## Next Action\n\n"
        "Activate the first eligible idle task.\n"
    )


class LifecycleTransactionTest(unittest.TestCase):
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
        ):
            source = REPO_ROOT / relative
            if not source.exists():
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def write_active_plan(self, root: Path, tasks: list[dict] | None = None) -> Path:
        plan_dir = root / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            "# PLAN-001: Lifecycle transaction\n\n"
            '<a id="task-001-section"></a>\n\n'
            "### TASK-001: Implement lifecycle transaction\n\n"
            '<a id="task-002-section"></a>\n\n'
            "### TASK-002: Extend lifecycle transaction\n",
            encoding="utf-8",
        )
        (plan_dir / "handoff.md").write_text(valid_handoff(), encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-001",
                    "planRef": "./plan.md",
                    "tasks": tasks or [task_fixture("TASK-001", "Implement lifecycle transaction")],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return plan_dir

    def write_state(self, root: Path, state: dict | None = None) -> Path:
        state_path = root / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state or workflow_state("planning", "planner", None), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return state_path

    def run_transaction(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
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

    def test_activate_next_updates_task_state_workflow_state_and_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            plan_dir = self.write_active_plan(root)
            state_path = self.write_state(root)

            result = self.run_transaction(root, "activate-next")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            tasks = json.loads((plan_dir / "tasks.json").read_text(encoding="utf-8"))
            task = tasks["tasks"][0]
            self.assertEqual(task["status"], "implementing")
            self.assertEqual(task["ownerRole"], "developer")
            self.assertEqual(task["nextAction"], "执行 TASK-001")

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["currentPhase"], "implementing")
            self.assertEqual(state["ownerRole"], "developer")
            self.assertEqual(state["activeTaskId"], "TASK-001")
            self.assertEqual(state["nextAction"], "执行 TASK-001")

            handoff = (plan_dir / "handoff.md").read_text(encoding="utf-8")
            self.assertIn("activate-next", handoff)
            self.assertIn("TASK-001", handoff)
            self.assertIn("planner -> developer", handoff)

    def test_start_testing_updates_active_task_and_workflow_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            plan_dir = self.write_active_plan(
                root,
                [task_fixture("TASK-001", "Implement lifecycle transaction", status="implementing")],
            )
            state_path = self.write_state(root, workflow_state("implementing", "developer", "TASK-001"))

            result = self.run_transaction(root, "start-testing")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            task = json.loads((plan_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
            self.assertEqual(task["status"], "testing")
            self.assertEqual(task["ownerRole"], "tester")
            self.assertEqual(task["nextAction"], "运行 TASK-001 验证")

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["currentPhase"], "testing")
            self.assertEqual(state["ownerRole"], "tester")
            self.assertEqual(state["activeTaskId"], "TASK-001")

    def test_start_testing_rejects_paused_workflow_without_mutating_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            plan_dir = self.write_active_plan(
                root,
                [task_fixture("TASK-001", "Implement lifecycle transaction", status="implementing")],
            )
            state_path = self.write_state(
                root,
                workflow_state(
                    "implementing",
                    "developer",
                    "TASK-001",
                    workflow_status="paused",
                ),
            )
            before_state = state_path.read_text(encoding="utf-8")
            before_tasks = (plan_dir / "tasks.json").read_text(encoding="utf-8")

            result = self.run_transaction(root, "start-testing")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("workflowStatus", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before_state)
            self.assertEqual((plan_dir / "tasks.json").read_text(encoding="utf-8"), before_tasks)

    def test_review_passed_marks_current_done_and_enters_archiving_when_no_tasks_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            plan_dir = self.write_active_plan(
                root,
                [task_fixture("TASK-001", "Implement lifecycle transaction", status="reviewing", review_result="passed")],
            )
            state_path = self.write_state(root, workflow_state("reviewing", "reviewer", "TASK-001"))

            result = self.run_transaction(root, "review-passed")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["commitGate"]["required"], True)
            self.assertEqual(payload["commitGate"]["taskId"], "TASK-001")
            self.assertIn("commit-task --task TASK-001", payload["commitGate"]["command"])
            task = json.loads((plan_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
            self.assertEqual(task["status"], "done")
            self.assertEqual(task["verification"]["lastResult"], "passed")
            self.assertEqual(task["review"]["lastResult"], "passed")

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["currentPhase"], "archiving")
            self.assertEqual(state["ownerRole"], "developer")
            self.assertIsNone(state["activeTaskId"])

    def test_start_review_requires_passed_verification_and_moves_to_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            plan_dir = self.write_active_plan(
                root,
                [task_fixture("TASK-001", "Implement lifecycle transaction", status="testing")],
            )
            tasks = json.loads((plan_dir / "tasks.json").read_text(encoding="utf-8"))
            tasks["tasks"][0]["verification"]["lastResult"] = "passed"
            (plan_dir / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            state_path = self.write_state(root, workflow_state("testing", "tester", "TASK-001"))

            result = self.run_transaction(root, "start-review")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            task = json.loads((plan_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
            self.assertEqual(task["status"], "reviewing")
            self.assertEqual(task["ownerRole"], "reviewer")

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["currentPhase"], "reviewing")
            self.assertEqual(state["ownerRole"], "reviewer")

    def test_review_passed_requires_structured_review_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            self.write_active_plan(
                root,
                [task_fixture("TASK-001", "Implement lifecycle transaction", status="reviewing")],
            )
            state_path = self.write_state(root, workflow_state("reviewing", "reviewer", "TASK-001"))
            before = state_path.read_text(encoding="utf-8")

            result = self.run_transaction(root, "review-passed")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("review.lastResult", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_review_failed_returns_active_task_to_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            plan_dir = self.write_active_plan(
                root,
                [task_fixture("TASK-001", "Implement lifecycle transaction", status="reviewing", review_result="failed")],
            )
            state_path = self.write_state(root, workflow_state("reviewing", "reviewer", "TASK-001"))

            result = self.run_transaction(root, "review-failed")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            task = json.loads((plan_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
            self.assertEqual(task["status"], "implementing")
            self.assertEqual(task["ownerRole"], "developer")

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["currentPhase"], "implementing")
            self.assertEqual(state["ownerRole"], "developer")


if __name__ == "__main__":
    unittest.main()
