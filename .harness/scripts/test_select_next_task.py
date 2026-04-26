#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SELECT_NEXT_TASK = REPO_ROOT / ".harness" / "scripts" / "select-next-task.py"
TASKS_SCHEMA = REPO_ROOT / ".harness" / "schemas" / "tasks.schema.json"


def base_task(task_id: str, *, depends_on: list[str] | None = None) -> dict:
    slug = task_id.lower()
    return {
        "taskId": task_id,
        "title": f"Task {task_id}",
        "planSection": f"{slug}-section",
        "status": "idle",
        "currentStep": "",
        "nextAction": "",
        "ownerRole": "developer",
        "dependsOn": depends_on or [],
        "files": {"create": [], "modify": [f"src/{slug}.py"], "test": []},
        "acceptance": [f"{task_id} acceptance is met"],
        "verification": {
            "commands": [],
            "checks": ["baseline check exists"],
            "lastResult": "not_run",
        },
        "blockedReason": "",
    }


def mark_done(task: dict) -> None:
    task["status"] = "done"
    task["currentStep"] = "Accepted"
    task["nextAction"] = ""
    task["verification"]["lastResult"] = "passed"
    task["verification"]["checks"] = [f"{task['taskId']} verification passed"]


def base_manifest() -> dict:
    return {
        "$schema": "../../../../.harness/schemas/tasks.schema.json",
        "planId": "PLAN-001",
        "planRef": "./plan.md",
        "tasks": [
            base_task("TASK-001"),
            base_task("TASK-002", depends_on=["TASK-001"]),
            base_task("TASK-003"),
        ],
    }


class SelectNextTaskTest(unittest.TestCase):
    def write_tasks(self, tmp: str, manifest: dict | None = None) -> Path:
        plan_dir = Path(tmp) / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        tasks_path = plan_dir / "tasks.json"
        tasks_path.write_text(
            json.dumps(manifest or base_manifest(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return tasks_path

    def run_select(self, tasks_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SELECT_NEXT_TASK),
                "--tasks",
                str(tasks_path),
                "--schema",
                str(TASKS_SCHEMA),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_selects_first_idle_task_with_done_dependencies_without_writing(self) -> None:
        manifest = base_manifest()
        mark_done(manifest["tasks"][0])

        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp, manifest)
            before = tasks_path.read_text(encoding="utf-8")

            result = self.run_select(tasks_path)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(result.stdout)
            self.assertEqual(data["kind"], "task")
            self.assertEqual(data["task"]["taskId"], "TASK-002")
            self.assertEqual(
                data["taskUpdate"],
                {
                    "taskId": "TASK-002",
                    "status": "implementing",
                    "ownerRole": "developer",
                    "nextAction": "执行 TASK-002: Task TASK-002",
                },
            )
            self.assertEqual(
                data["statePatch"],
                [
                    {"op": "replace", "path": "/currentPhase", "value": "implementing"},
                    {"op": "replace", "path": "/ownerRole", "value": "developer"},
                    {"op": "replace", "path": "/activeTaskId", "value": "TASK-002"},
                    {"op": "replace", "path": "/nextAction", "value": "执行 TASK-002: Task TASK-002"},
                ],
            )
            self.assertEqual(tasks_path.read_text(encoding="utf-8"), before)

    def test_skips_blocked_idle_task_and_selects_later_executable_task(self) -> None:
        manifest = base_manifest()
        manifest["tasks"][0]["status"] = "blocked"
        manifest["tasks"][0]["blockedReason"] = "Waiting for external input"

        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp, manifest)

            result = self.run_select(tasks_path)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(result.stdout)
            self.assertEqual(data["kind"], "task")
            self.assertEqual(data["task"]["taskId"], "TASK-003")

    def test_rejects_when_an_active_task_already_exists(self) -> None:
        manifest = base_manifest()
        manifest["tasks"][0]["status"] = "implementing"

        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp, manifest)
            before = tasks_path.read_text(encoding="utf-8")

            result = self.run_select(tasks_path)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("active task already exists", result.stderr + result.stdout)
            self.assertEqual(tasks_path.read_text(encoding="utf-8"), before)

    def test_reports_no_executable_idle_task_when_dependencies_are_blocked(self) -> None:
        manifest = base_manifest()
        manifest["tasks"] = [
            base_task("TASK-001"),
            base_task("TASK-002", depends_on=["TASK-001"]),
        ]
        manifest["tasks"][0]["status"] = "blocked"
        manifest["tasks"][0]["blockedReason"] = "Waiting for external input"

        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp, manifest)
            before = tasks_path.read_text(encoding="utf-8")

            result = self.run_select(tasks_path)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("no executable idle task", result.stderr + result.stdout)
            self.assertEqual(tasks_path.read_text(encoding="utf-8"), before)

    def test_outputs_archive_patch_when_all_tasks_are_done(self) -> None:
        manifest = base_manifest()
        for task in manifest["tasks"]:
            mark_done(task)

        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp, copy.deepcopy(manifest))

            result = self.run_select(tasks_path)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(result.stdout)
            self.assertEqual(data["kind"], "archive")
            self.assertIsNone(data["task"])
            self.assertEqual(
                data["statePatch"],
                [
                    {"op": "replace", "path": "/currentPhase", "value": "archiving"},
                    {"op": "replace", "path": "/ownerRole", "value": "developer"},
                    {"op": "replace", "path": "/activeTaskId", "value": None},
                    {"op": "replace", "path": "/nextAction", "value": "归档当前 plan package"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
