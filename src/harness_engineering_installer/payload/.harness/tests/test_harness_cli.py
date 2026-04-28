#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "harness"


def direct_state(*, next_action: str = "Run targeted regression test") -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-fix-login-20260427-v1",
        "activePlanRef": None,
        "activeTaskId": None,
        "workflowStatus": "active",
        "currentPhase": "implementing",
        "ownerRole": "developer",
        "nextAction": next_action,
        "updatedAt": "2026-04-27T09:00:00+08:00",
    }


class HarnessCliTest(unittest.TestCase):
    def write_harness_assets(self, root: Path) -> None:
        for relative in (
            ".harness/schemas/workflow-state.schema.json",
            ".harness/schemas/tasks.schema.json",
            ".harness/schemas/backlogs.schema.json",
            ".harness/schemas/backlog-consumption-event.schema.json",
            ".harness/schemas/project-contracts.schema.json",
            ".harness/schemas/project-entrypoints.schema.json",
            ".harness/templates/backlogs.template.json",
            ".harness/templates/project-contracts.template.json",
            ".harness/templates/project-entrypoints.template.json",
            ".harness/scripts/lint-harness.py",
            ".harness/scripts/validate-state.py",
            ".harness/scripts/state-write.py",
            ".harness/scripts/lifecycle-transaction.py",
            ".harness/scripts/commit-task.py",
            ".harness/scripts/session-start.py",
            ".harness/scripts/start-workflow.py",
            ".harness/scripts/archive-plan.py",
            ".harness/scripts/complete-workflow.py",
            ".harness/scripts/backlog-intake.py",
            ".harness/scripts/backlog-consume.py",
            ".harness/scripts/check-project-env.py",
            ".harness/scripts/init-project-entrypoint.py",
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

    def run_harness(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
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

    def test_lint_delegates_to_lint_harness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_harness(root, "lint")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Harness lint 校验通过", result.stdout)

    def test_transition_help_delegates_to_lifecycle_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_harness(root, "transition", "--help")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Coordinate Harness lifecycle artifact transitions", result.stdout)
            self.assertIn("activate-next", result.stdout)

    def test_validate_state_defaults_to_workflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            self.write_state(root, direct_state(next_action="优化流程"))

            result = self.run_harness(root, "validate-state")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("workflow-state.json", result.stdout + result.stderr)
            self.assertIn("优化流程", result.stdout + result.stderr)

    def test_help_lists_backlog_intake_subcommand(self) -> None:
        result = self.run_harness(REPO_ROOT, "--help")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("backlog-intake", result.stdout)
        self.assertIn("backlog-consume", result.stdout)
        self.assertIn("commit-task", result.stdout)
        self.assertIn("check-project-env", result.stdout)
        self.assertIn("init-entrypoint", result.stdout)
        self.assertIn("start-workflow", result.stdout)

    def test_commit_task_help_delegates_to_commit_task_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_harness(root, "commit-task", "--help")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Commit a completed Harness task", result.stdout)

    def test_check_project_env_help_delegates_to_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_harness(root, "check-project-env", "--help")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Validate and execute project environment contracts", result.stdout)

    def test_init_entrypoint_help_delegates_to_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_harness(root, "init-entrypoint", "--help")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Detect or update Harness project entrypoints", result.stdout)

    def test_backlog_intake_delegates_to_backlog_intake_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_harness(
                root,
                "backlog-intake",
                "--title",
                "Queued follow-up",
                "--summary",
                "Record a follow-up item through the unified CLI.",
                "--dispatch",
                "queue",
                "--source-ref",
                "chat:2026-04-27-003",
                "--created-at",
                "2026-04-27T11:00:00+08:00",
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn('"id": "BL-001"', result.stdout)
            store = json.loads((root / "work" / "backlog" / "backlogs.json").read_text(encoding="utf-8"))
            self.assertEqual(store["items"][0]["title"], "Queued follow-up")

    def test_backlog_consume_help_delegates_to_backlog_consume_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_harness(root, "backlog-consume", "--help")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Consume a pending Harness backlog item", result.stdout)


if __name__ == "__main__":
    unittest.main()
