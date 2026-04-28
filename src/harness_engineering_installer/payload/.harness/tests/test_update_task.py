#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_TASK = REPO_ROOT / ".harness" / "scripts" / "update-task.py"
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


def passed_review() -> dict:
    review = default_review()
    review["score"] = 90
    review["lastResult"] = "passed"
    review["checks"] = ["review gate passed"]
    review["reportRef"] = "work/sessions/2026-04-27/session-review.md"
    return review


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
        "review": default_review(),
        "blockedReason": "",
    }


def base_manifest() -> dict:
    return {
        "$schema": "../../../../.harness/schemas/tasks.schema.json",
        "planId": "PLAN-001",
        "planRef": "./plan.md",
        "tasks": [
            base_task("TASK-001"),
            base_task("TASK-002", depends_on=["TASK-001"]),
        ],
    }


class UpdateTaskTest(unittest.TestCase):
    def write_tasks(self, tmp: str, manifest: dict | None = None) -> Path:
        plan_dir = Path(tmp) / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        tasks_path = plan_dir / "tasks.json"
        tasks_path.write_text(
            json.dumps(manifest or base_manifest(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return tasks_path

    def run_update(self, tasks_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(UPDATE_TASK),
                "--tasks",
                str(tasks_path),
                "--schema",
                str(TASKS_SCHEMA),
                *args,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def assert_schema_valid(self, data: dict) -> None:
        schema = json.loads(TASKS_SCHEMA.read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(data))
        self.assertEqual(errors, [])

    def test_updates_task_status_role_and_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp)

            result = self.run_update(
                tasks_path,
                "--task",
                "TASK-001",
                "--status",
                "testing",
                "--current-step",
                "Implementation ready for verification",
                "--next-action",
                "Run task verification command",
                "--verification-last-result",
                "failed",
                "--verification-command",
                "python3 .harness/tests/test_update_task.py",
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.assert_schema_valid(data)
            task = data["tasks"][0]
            self.assertEqual(task["status"], "testing")
            self.assertEqual(task["ownerRole"], "tester")
            self.assertEqual(task["currentStep"], "Implementation ready for verification")
            self.assertEqual(task["nextAction"], "Run task verification command")
            self.assertEqual(task["verification"]["lastResult"], "failed")
            self.assertEqual(
                task["verification"]["commands"],
                ["python3 .harness/tests/test_update_task.py"],
            )

    def test_updates_review_gate_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp)

            result = self.run_update(
                tasks_path,
                "--task",
                "TASK-001",
                "--review-score",
                "92",
                "--review-last-result",
                "passed",
                "--review-check",
                "schema, scripts, and tests are synchronized",
                "--review-finding-json",
                '{"severity":"important","blocking":false,"summary":"Document follow-up","deferReason":"Tracked in handoff"}',
                "--review-report-ref",
                "work/sessions/2026-04-27/session-review.md",
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.assert_schema_valid(data)
            review = data["tasks"][0]["review"]
            self.assertEqual(review["score"], 92)
            self.assertEqual(review["lastResult"], "passed")
            self.assertEqual(review["checks"], ["schema, scripts, and tests are synchronized"])
            self.assertEqual(review["findings"][0]["severity"], "important")
            self.assertFalse(review["findings"][0]["blocking"])
            self.assertEqual(review["reportRef"], "work/sessions/2026-04-27/session-review.md")

    def test_rejects_done_when_dependency_is_not_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp)
            before = tasks_path.read_text(encoding="utf-8")

            result = self.run_update(
                tasks_path,
                "--task",
                "TASK-002",
                "--status",
                "done",
                "--verification-last-result",
                "passed",
                "--verification-check",
                "TASK-002 verification passed",
                "--review-score",
                "90",
                "--review-last-result",
                "passed",
                "--review-check",
                "TASK-002 review passed",
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("dependsOn", result.stderr + result.stdout)
            self.assertEqual(tasks_path.read_text(encoding="utf-8"), before)

    def test_rejects_unknown_task_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp)
            before = tasks_path.read_text(encoding="utf-8")

            result = self.run_update(
                tasks_path,
                "--task",
                "TASK-999",
                "--status",
                "implementing",
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("unknown taskId", result.stderr + result.stdout)
            self.assertEqual(tasks_path.read_text(encoding="utf-8"), before)

    def test_marks_done_when_dependencies_are_done_and_verification_passed(self) -> None:
        manifest = base_manifest()
        manifest["tasks"][0]["status"] = "done"
        manifest["tasks"][0]["verification"]["lastResult"] = "passed"
        manifest["tasks"][0]["verification"]["checks"] = ["TASK-001 verification passed"]
        manifest["tasks"][0]["review"] = passed_review()

        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp, copy.deepcopy(manifest))

            result = self.run_update(
                tasks_path,
                "--task",
                "TASK-002",
                "--status",
                "done",
                "--current-step",
                "Verification passed",
                "--next-action",
                "",
                "--verification-last-result",
                "passed",
                "--verification-check",
                "TASK-002 verification passed",
                "--review-score",
                "90",
                "--review-last-result",
                "passed",
                "--review-check",
                "TASK-002 review passed",
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.assert_schema_valid(data)
            self.assertEqual(data["tasks"][1]["status"], "done")
            self.assertEqual(data["tasks"][1]["verification"]["lastResult"], "passed")
            self.assertEqual(data["tasks"][1]["review"]["lastResult"], "passed")

    def test_rejects_done_when_review_gate_has_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = self.write_tasks(tmp)
            before = tasks_path.read_text(encoding="utf-8")

            result = self.run_update(
                tasks_path,
                "--task",
                "TASK-001",
                "--status",
                "done",
                "--verification-last-result",
                "passed",
                "--verification-check",
                "TASK-001 verification passed",
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("review", result.stderr + result.stdout)
            self.assertEqual(tasks_path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
