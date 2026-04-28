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
SESSION_START_RULE = REPO_ROOT / ".harness" / "rules" / "session-start.md"


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
        "The active plan exists but workflow state is missing.\n"
        "\n"
        "## Role Handoff\n\n"
        "- fromRole: planner\n"
        "- toRole: developer\n"
        "- reason: test fixture for missing state recovery\n"
        "- stateSource: workflow-state.json and tasks.json\n"
        "\n"
        "## Risks\n\n"
        "- session-start.py must not guess state from active plan files.\n"
        "\n"
        "## Next Action\n\n"
        "Block startup and request semantic recovery.\n"
    )


class SessionStartTest(unittest.TestCase):
    def write_harness_assets(self, root: Path) -> None:
        for relative in (
            ".harness/schemas/workflow-state.schema.json",
            ".harness/schemas/tasks.schema.json",
            ".harness/schemas/backlogs.schema.json",
            ".harness/schemas/backlog-consumption-event.schema.json",
            ".harness/schemas/project-contracts.schema.json",
            ".harness/schemas/project-entrypoints.schema.json",
            ".harness/templates/workflow-state.template.json",
            ".harness/templates/backlogs.template.json",
            ".harness/templates/project-contracts.template.json",
            ".harness/templates/project-entrypoints.template.json",
            ".harness/templates/entrypoint-managed-block.template.md",
            ".harness/templates/plan.template.md",
            ".harness/templates/tasks.template.json",
            ".harness/templates/handoff.template.md",
            ".harness/templates/closure.template.md",
            ".harness/rules/workflow-lifecycle.md",
            ".harness/rules/archive-rules.md",
            ".harness/rules/backlog-rules.md",
            ".harness/rules/handoff-rules.md",
            ".harness/rules/session-start.md",
            ".harness/skills/project-init/SKILL.md",
            ".harness/skills/project-env-contract/SKILL.md",
            ".harness/skills/plan-writing/SKILL.md",
            ".harness/skills/task-review/SKILL.md",
            ".harness/scripts/lint-harness.py",
            ".harness/scripts/validate-state.py",
            ".harness/scripts/state-write.py",
            ".harness/scripts/start-workflow.py",
            ".harness/scripts/update-task.py",
            ".harness/scripts/select-next-task.py",
            ".harness/scripts/materialize-tasks.py",
            ".harness/scripts/lifecycle-transaction.py",
            ".harness/scripts/commit-task.py",
            ".harness/scripts/archive-plan.py",
            ".harness/scripts/complete-workflow.py",
            ".harness/scripts/backlog-intake.py",
            ".harness/scripts/backlog-consume.py",
            ".harness/scripts/check-project-env.py",
            ".harness/scripts/init-project-entrypoint.py",
            ".harness/scripts/harness",
            ".harness/scripts/session-start.py",
            ".harness/ARCHITECTURE.md",
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
        (plan_dir / "handoff.md").write_text(valid_handoff(), encoding="utf-8")
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

    def test_missing_backlog_intake_assets_are_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            (root / ".harness" / "rules" / "backlog-rules.md").unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/rules/backlog-rules.md", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_missing_backlog_consumption_assets_are_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            for relative in (
                ".harness/schemas/backlog-consumption-event.schema.json",
                ".harness/scripts/backlog-consume.py",
            ):
                (root / relative).unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/schemas/backlog-consumption-event.schema.json", result.stderr + result.stdout)
            self.assertIn(".harness/scripts/backlog-consume.py", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_missing_handoff_and_session_rule_assets_are_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            for relative in (
                ".harness/rules/handoff-rules.md",
                ".harness/rules/session-start.md",
            ):
                path = root / relative
                if path.exists():
                    path.unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/rules/handoff-rules.md", result.stderr + result.stdout)
            self.assertIn(".harness/rules/session-start.md", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_session_start_does_not_require_installer_lifecycle_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((root / "work" / "workflow-state.json").exists())

    def test_missing_project_init_skill_asset_is_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            (root / ".harness" / "skills" / "project-init" / "SKILL.md").unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/skills/project-init/SKILL.md", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_missing_project_env_contract_skill_asset_is_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            (root / ".harness" / "skills" / "project-env-contract" / "SKILL.md").unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/skills/project-env-contract/SKILL.md", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_missing_plan_writing_and_task_review_skill_assets_are_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            for relative in (
                ".harness/skills/plan-writing/SKILL.md",
                ".harness/skills/task-review/SKILL.md",
            ):
                (root / relative).unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/skills/plan-writing/SKILL.md", result.stderr + result.stdout)
            self.assertIn(".harness/skills/task-review/SKILL.md", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_missing_project_contract_runner_assets_are_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            for relative in (
                ".harness/schemas/project-contracts.schema.json",
                ".harness/templates/project-contracts.template.json",
                ".harness/scripts/check-project-env.py",
            ):
                (root / relative).unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/schemas/project-contracts.schema.json", result.stderr + result.stdout)
            self.assertIn(".harness/templates/project-contracts.template.json", result.stderr + result.stdout)
            self.assertIn(".harness/scripts/check-project-env.py", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_missing_project_entrypoint_assets_are_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            for relative in (
                ".harness/schemas/project-entrypoints.schema.json",
                ".harness/templates/project-entrypoints.template.json",
                ".harness/templates/entrypoint-managed-block.template.md",
                ".harness/scripts/init-project-entrypoint.py",
            ):
                (root / relative).unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/schemas/project-entrypoints.schema.json", result.stderr + result.stdout)
            self.assertIn(".harness/templates/project-entrypoints.template.json", result.stderr + result.stdout)
            self.assertIn(".harness/templates/entrypoint-managed-block.template.md", result.stderr + result.stdout)
            self.assertIn(".harness/scripts/init-project-entrypoint.py", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_missing_harness_architecture_asset_is_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            (root / ".harness" / "ARCHITECTURE.md").unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/ARCHITECTURE.md", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_missing_commit_task_asset_is_blocked_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            (root / ".harness" / "scripts" / "commit-task.py").unlink()

            result = self.run_session_start(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn(".harness/scripts/commit-task.py", result.stderr + result.stdout)
            self.assertFalse((root / "work" / "workflow-state.json").exists())

    def test_session_start_rule_documents_startup_boundaries(self) -> None:
        text = SESSION_START_RULE.read_text(encoding="utf-8")

        self.assertIn("validate existing state", text)
        self.assertIn("bootstrap missing state", text)
        self.assertIn("block missing state with active plan", text)
        self.assertIn("must not modify existing workflow-state.json", text)
        self.assertIn("session audit file", text)
        self.assertIn("not a truth source", text)

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
