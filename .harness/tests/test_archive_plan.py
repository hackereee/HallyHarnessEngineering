#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "archive-plan.py"


def done_task(task_id: str) -> dict:
    slug = task_id.lower()
    return {
        "taskId": task_id,
        "title": f"Task {task_id}",
        "planSection": f"{slug}-section",
        "status": "done",
        "currentStep": "Review passed",
        "nextAction": "",
        "ownerRole": "developer",
        "dependsOn": [],
        "files": {"create": [], "modify": [f"src/{slug}.py"], "test": []},
        "acceptance": [f"{task_id} acceptance is met"],
        "verification": {
            "commands": ["python3 -m unittest discover -s .harness/tests -p 'test_*.py'"],
            "checks": [],
            "lastResult": "passed",
        },
        "blockedReason": "",
    }


def archiving_state() -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-plan-001-v1",
        "activePlanRef": "./plans/active/PLAN-001/plan.md",
        "activeTaskId": None,
        "workflowStatus": "active",
        "currentPhase": "archiving",
        "ownerRole": "developer",
        "nextAction": "归档当前 plan package",
        "updatedAt": "2026-04-27T09:00:00+08:00",
    }


class ArchivePlanTest(unittest.TestCase):
    def write_harness_assets(self, root: Path) -> None:
        for relative in (
            ".harness/schemas/workflow-state.schema.json",
            ".harness/schemas/tasks.schema.json",
            ".harness/templates/closure.template.md",
            ".harness/rules/workflow-lifecycle.md",
            ".harness/rules/archive-rules.md",
            ".harness/scripts/lint-harness.py",
            ".harness/scripts/validate-state.py",
            ".harness/scripts/state-write.py",
            ".harness/scripts/archive-plan.py",
        ):
            source = REPO_ROOT / relative
            if not source.exists():
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def write_active_plan(self, root: Path, *, include_closure: bool = True) -> Path:
        plan_dir = root / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            "# PLAN-001: Archive plan\n\n"
            '<a id="task-001-section"></a>\n\n'
            "### TASK-001: Task TASK-001\n",
            encoding="utf-8",
        )
        (plan_dir / "handoff.md").write_text("# Handoff\n", encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-001",
                    "planRef": "./plan.md",
                    "tasks": [done_task("TASK-001")],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if include_closure:
            (plan_dir / "closure.md").write_text(
                "# Closure\n\n"
                "- workflowId: workflow-plan-001-v1\n"
                "- planId: PLAN-001\n"
                "- result: completed\n\n"
                "## Delivered\n\n"
                "- Implemented TASK-001.\n\n"
                "## Verification Evidence\n\n"
                "- `python3 -m unittest discover -s .harness/tests -p 'test_*.py'` passed.\n\n"
                "## Review Summary\n\n"
                "- Review passed.\n\n"
                "## Deviations\n\n"
                "- None.\n\n"
                "## Follow-ups\n\n"
                "- None.\n",
                encoding="utf-8",
            )
        return plan_dir

    def write_state(self, root: Path) -> Path:
        state_path = root / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(archiving_state(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return state_path

    def run_archive(self, root: Path, plan_id: str = "PLAN-001") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                plan_id,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_archives_active_plan_and_updates_workflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            active_dir = self.write_active_plan(root)
            state_path = self.write_state(root)

            result = self.run_archive(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertFalse(active_dir.exists())
            archived_dir = root / "work" / "plans" / "archived" / "PLAN-001"
            self.assertTrue(archived_dir.exists())
            self.assertTrue((archived_dir / "closure.md").exists())

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["workflowStatus"], "archived")
            self.assertEqual(state["currentPhase"], "archiving")
            self.assertIsNone(state["activePlanRef"])
            self.assertIsNone(state["activeTaskId"])
            self.assertEqual(state["nextAction"], "开启下一个 workflow")

    def test_rejects_missing_closure_without_moving_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            active_dir = self.write_active_plan(root, include_closure=False)
            self.write_state(root)

            result = self.run_archive(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("closure.md", result.stderr + result.stdout)
            self.assertTrue(active_dir.exists())
            self.assertFalse((root / "work" / "plans" / "archived" / "PLAN-001").exists())


if __name__ == "__main__":
    unittest.main()
