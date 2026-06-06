#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "complete-workflow.py"


def direct_reviewing_state() -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-fix-login-20260427-v1",
        "activePlanRef": None,
        "activeTaskId": None,
        "workflowStatus": "active",
        "currentPhase": "reviewing",
        "ownerRole": "reviewer",
        "nextAction": "Review L1 fix result",
        "updatedAt": "2026-04-27T09:00:00+08:00",
    }


def plan_reviewing_state() -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-plan-001-v1",
        "activePlanRef": "./plans/active/PLAN-001/plan.md",
        "activeTaskId": "TASK-001",
        "workflowStatus": "active",
        "currentPhase": "reviewing",
        "ownerRole": "reviewer",
        "nextAction": "Review TASK-001 deliverables",
        "updatedAt": "2026-04-27T09:00:00+08:00",
    }


def reviewing_task() -> dict:
    return {
        "taskId": "TASK-001",
        "title": "Implement planned workflow",
        "planSection": "task-001-section",
        "status": "reviewing",
        "currentStep": "Verification passed",
        "nextAction": "Review TASK-001 deliverables",
        "ownerRole": "reviewer",
        "dependsOn": [],
        "files": {"create": [], "modify": ["src/example.py"], "test": []},
        "acceptance": ["Planned workflow is implemented"],
        "verification": {
            "commands": ["python3 .harness/tests/test_validate_state.py"],
            "checks": [],
            "lastResult": "passed",
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
        "- workflowId: workflow-plan-001-v1\n"
        "- planRef: ./plans/active/PLAN-001/plan.md\n"
        "- activeTaskId: TASK-001\n"
        "- currentPhase: reviewing\n"
        "- taskStatus: TASK-001 reviewing\n"
        "- ownerRole: reviewer\n"
        "- sourceSessionId: session-test\n"
        "\n"
        "## Current Status\n\n"
        "The active task is in review.\n"
        "\n"
        "## Role Handoff\n\n"
        "- fromRole: tester\n"
        "- toRole: reviewer\n"
        "- reason: verification passed\n"
        "- stateSource: workflow-state.json and tasks.json\n"
        "\n"
        "## Risks\n\n"
        "- Plan-backed workflows must not use complete-workflow.py.\n"
        "\n"
        "## Next Action\n\n"
        "Review the active task.\n"
    )


class CompleteWorkflowTest(unittest.TestCase):
    def write_harness_assets(self, root: Path) -> None:
        for relative in (
            ".harness/schemas/workflow-state.schema.json",
            ".harness/schemas/tasks.schema.json",
            ".harness/rules/workflow-lifecycle.md",
            ".harness/rules/archive-rules.md",
            ".harness/scripts/lint-harness.py",
            ".harness/scripts/validate-state.py",
            ".harness/scripts/state-write.py",
            ".harness/scripts/complete-workflow.py",
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

    def write_active_plan(self, root: Path) -> Path:
        plan_dir = root / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            "# PLAN-001: Planned workflow\n\n"
            '<a id="task-001-section"></a>\n\n'
            "### TASK-001: Implement planned workflow\n",
            encoding="utf-8",
        )
        (plan_dir / "handoff.md").write_text(valid_handoff(), encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-001",
                    "planRef": "./plan.md",
                    "tasks": [reviewing_task()],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return plan_dir

    def run_complete(self, root: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                "--timestamp",
                "2026-04-27T09:30:00+08:00",
                *extra_args,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_completes_direct_workflow_and_writes_audit_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = self.write_state(root, direct_reviewing_state())

            result = self.run_complete(
                root,
                "--verification-command",
                "python3 .harness/tests/test_validate_state.py",
                "--review-summary",
                "Review passed for the L1 workflow.",
                "--architecture-impact",
                "Target project architecture unchanged; Harness framework architecture unchanged.",
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["workflowStatus"], "completed")
            self.assertEqual(state["currentPhase"], "reviewing")
            self.assertEqual(state["ownerRole"], "reviewer")
            self.assertIsNone(state["activePlanRef"])
            self.assertIsNone(state["activeTaskId"])
            self.assertEqual(state["nextAction"], "Start next workflow")

            audit_path = root / "work" / "sessions" / "2026-04-27" / "workflow-completions.jsonl"
            self.assertTrue(audit_path.exists())
            audit = json.loads(audit_path.read_text(encoding="utf-8").strip())
            self.assertEqual(audit["workflowId"], "workflow-fix-login-20260427-v1")
            self.assertEqual(audit["workflowStatus"], "completed")
            self.assertEqual(
                audit["verification"]["commands"],
                ["python3 .harness/tests/test_validate_state.py"],
            )
            self.assertEqual(audit["reviewSummary"], "Review passed for the L1 workflow.")
            self.assertEqual(
                audit["architectureImpact"],
                "Target project architecture unchanged; Harness framework architecture unchanged.",
            )

    def test_rejects_missing_architecture_impact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = self.write_state(root, direct_reviewing_state())
            original = state_path.read_text(encoding="utf-8")

            result = self.run_complete(
                root,
                "--verification-check",
                "direct workflow verification passed",
                "--review-summary",
                "Review passed.",
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("architecture impact", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)

    def test_rejects_plan_backed_workflow_without_moving_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            self.write_active_plan(root)
            state_path = self.write_state(root, plan_reviewing_state())
            original = state_path.read_text(encoding="utf-8")

            result = self.run_complete(
                root,
                "--verification-check",
                "planned workflow verification passed",
                "--review-summary",
                "Review passed.",
                "--architecture-impact",
                "Planned workflow architecture impact belongs in closure.md.",
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("applies only to L0/L1", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)

    def test_rejects_unwritable_completion_audit_without_completing_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = self.write_state(root, direct_reviewing_state())
            original = state_path.read_text(encoding="utf-8")
            audit_path = root / "work" / "sessions" / "2026-04-27" / "workflow-completions.jsonl"
            audit_path.mkdir(parents=True)

            result = self.run_complete(
                root,
                "--verification-check",
                "direct workflow verification passed",
                "--review-summary",
                "Review passed.",
                "--architecture-impact",
                "Target project architecture unchanged; Harness framework architecture unchanged.",
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("workflow-completions.jsonl", result.stderr + result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
