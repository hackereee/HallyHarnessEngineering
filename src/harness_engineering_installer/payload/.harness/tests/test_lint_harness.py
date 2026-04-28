#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "lint-harness.py"
WORKFLOW_SCHEMA = REPO_ROOT / ".harness" / "schemas" / "workflow-state.schema.json"
TASKS_SCHEMA = REPO_ROOT / ".harness" / "schemas" / "tasks.schema.json"


def default_review() -> dict:
    return {
        "score": 0,
        "threshold": 85,
        "lastResult": "not_run",
        "rubricVersion": "review-rubric-v1",
        "checks": [],
        "findings": [],
        "reportRef": "",
    }


def base_task(task_id: str, status: str = "idle", owner_role: str = "developer") -> dict:
    return {
        "taskId": task_id,
        "title": f"Task {task_id}",
        "planSection": f"{task_id.lower()}-section",
        "status": status,
        "currentStep": "",
        "nextAction": "",
        "ownerRole": owner_role,
        "dependsOn": [],
        "files": {"create": [], "modify": [f"src/{task_id.lower()}.py"], "test": []},
        "acceptance": [f"{task_id} acceptance is met"],
        "verification": {
            "commands": [],
            "checks": ["baseline check exists"],
            "lastResult": "not_run",
        },
        "review": default_review(),
        "blockedReason": "",
    }


def base_state(
    *,
    active_plan_ref: str | None = "./plans/active/PLAN-001/plan.md",
    active_task_id: str | None = "TASK-001",
) -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-plan-001-v1",
        "activePlanRef": active_plan_ref,
        "activeTaskId": active_task_id,
        "workflowStatus": "active",
        "currentPhase": "implementing",
        "ownerRole": "developer",
        "nextAction": "Run task verification command",
        "updatedAt": "2026-04-25T20:00:00+08:00",
    }


def valid_handoff(plan_id: str = "PLAN-001") -> str:
    return (
        "# Handoff\n\n"
        "- workflowId: workflow-plan-001-v1\n"
        f"- planRef: ./plans/active/{plan_id}/plan.md\n"
        "- activeTaskId: TASK-001\n"
        "- currentPhase: implementing\n"
        "- taskStatus: TASK-001 implementing\n"
        "- ownerRole: developer\n"
        "- sourceSessionId: session-test\n"
        "\n"
        "## Current Status\n\n"
        "The active task is in implementation.\n"
        "\n"
        "## Role Handoff\n\n"
        "- fromRole: planner\n"
        "- toRole: developer\n"
        "- reason: task activation completed\n"
        "- stateSource: workflow-state.json and tasks.json\n"
        "\n"
        "## Risks\n\n"
        "- Keep state writes behind gateways.\n"
        "\n"
        "## Next Action\n\n"
        "Execute the active task.\n"
    )


class LintHarnessTest(unittest.TestCase):
    def write_harness_root(self, root: Path) -> None:
        schemas_dir = root / ".harness" / "schemas"
        scripts_dir = root / ".harness" / "scripts"
        schemas_dir.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)
        (schemas_dir / "workflow-state.schema.json").write_text(
            WORKFLOW_SCHEMA.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (schemas_dir / "tasks.schema.json").write_text(
            TASKS_SCHEMA.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def write_plan(
        self,
        root: Path,
        plan_id: str = "PLAN-001",
        tasks: list[dict] | None = None,
        *,
        include_handoff: bool = True,
    ) -> Path:
        plan_dir = root / "work" / "plans" / "active" / plan_id
        plan_dir.mkdir(parents=True)
        task_items = tasks or [base_task("TASK-001", "implementing", "developer")]
        anchors = "\n".join(
            f"<a id=\"{task['planSection']}\"></a>\n\n### {task['taskId']}: {task['title']}"
            for task in task_items
        )
        (plan_dir / "plan.md").write_text(f"# Plan\n\n{anchors}\n", encoding="utf-8")
        if include_handoff:
            (plan_dir / "handoff.md").write_text(valid_handoff(plan_id), encoding="utf-8")
        manifest = {
            "$schema": "../../../../.harness/schemas/tasks.schema.json",
            "planId": plan_id,
            "planRef": "./plan.md",
            "tasks": task_items,
        }
        (plan_dir / "tasks.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return plan_dir

    def write_state(self, root: Path, state: dict | None = None) -> Path:
        state_path = root / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state or base_state(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return state_path

    def run_lint(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_missing_work_directory_is_clean_initial_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("校验通过", result.stdout)

    def test_valid_active_plan_and_state_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            self.write_plan(root)
            self.write_state(root)

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_rejects_multiple_active_plan_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            self.write_plan(root, "PLAN-001")
            self.write_plan(root, "PLAN-002")
            self.write_state(root)

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("至多一个 active plan", result.stdout + result.stderr)

    def test_rejects_active_plan_when_state_has_no_active_plan_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            self.write_plan(root)
            self.write_state(root, base_state(active_plan_ref=None, active_task_id=None))

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("activePlanRef 为 null", result.stdout + result.stderr)

    def test_rejects_incomplete_active_plan_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            self.write_plan(root, include_handoff=False)
            self.write_state(root)

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("缺少 handoff.md", result.stdout + result.stderr)

    def test_rejects_active_plan_with_structurally_invalid_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            plan_dir = self.write_plan(root)
            (plan_dir / "handoff.md").write_text(
                "# Handoff\n\n"
                "- workflowId: workflow-plan-001-v1\n"
                "- planRef: ./plans/active/PLAN-001/plan.md\n"
                "\n"
                "## Current Status\n\n"
                "Missing required header fields and sections.\n",
                encoding="utf-8",
            )
            self.write_state(root)

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("handoff.md", result.stdout + result.stderr)
            self.assertIn("缺少必要字段", result.stdout + result.stderr)

    def test_rejects_handoff_fields_outside_top_metadata_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            plan_dir = self.write_plan(root)
            (plan_dir / "handoff.md").write_text(
                "# Handoff\n\n"
                "## Current Status\n\n"
                "- workflowId: workflow-plan-001-v1\n"
                "- planRef: ./plans/active/PLAN-001/plan.md\n"
                "- activeTaskId: TASK-001\n"
                "- currentPhase: implementing\n"
                "- taskStatus: TASK-001 implementing\n"
                "- ownerRole: developer\n"
                "- sourceSessionId: session-test\n"
                "\n"
                "## Role Handoff\n\n"
                "- fromRole: planner\n"
                "- toRole: developer\n"
                "- reason: task activation completed\n"
                "- stateSource: workflow-state.json and tasks.json\n"
                "\n"
                "## Risks\n\n"
                "- Keep state writes behind gateways.\n"
                "\n"
                "## Next Action\n\n"
                "Execute the active task.\n",
                encoding="utf-8",
            )
            self.write_state(root)

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("缺少必要字段", result.stdout + result.stderr)

    def test_rejects_multiple_active_tasks_in_tasks_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            self.write_plan(
                root,
                tasks=[
                    base_task("TASK-001", "implementing", "developer"),
                    base_task("TASK-002", "reviewing", "reviewer"),
                ],
            )
            self.write_state(root)

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("多个 active task", result.stdout + result.stderr)

    def test_rejects_direct_workflow_state_write_outside_state_write_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            bad_script = root / ".harness" / "scripts" / "bad-writer.py"
            bad_script.write_text(
                "from pathlib import Path\n"
                "state = Path('work') / 'workflow-state.json'\n"
                "state.write_text('{}')\n",
                encoding="utf-8",
            )

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("禁止直接写 workflow-state.json", result.stdout + result.stderr)

    def test_rejects_extensionless_script_writing_workflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_root(root)
            bad_script = root / ".harness" / "scripts" / "bad-writer"
            bad_script.write_text(
                "from pathlib import Path\n"
                "state = Path('work') / 'workflow-state.json'\n"
                "state.write_text('{}')\n",
                encoding="utf-8",
            )

            result = self.run_lint(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("bad-writer", result.stdout + result.stderr)
            self.assertIn("禁止直接写 workflow-state.json", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
