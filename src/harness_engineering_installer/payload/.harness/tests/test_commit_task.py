#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "commit-task.py"


def review_fixture(last_result: str = "passed") -> dict:
    return {
        "score": 90 if last_result == "passed" else 0,
        "threshold": 85,
        "lastResult": last_result,
        "rubricVersion": "review-rubric-v1",
        "checks": ["review passed"] if last_result == "passed" else [],
        "findings": [],
        "reportRef": "work/sessions/2026-04-27/session-review.md" if last_result == "passed" else "",
    }


def task_fixture(
    task_id: str,
    title: str,
    *,
    status: str = "done",
    review_result: str = "passed",
) -> dict:
    owner_by_status = {
        "idle": "developer",
        "implementing": "developer",
        "testing": "tester",
        "reviewing": "reviewer",
        "done": "developer",
    }
    return {
        "taskId": task_id,
        "title": title,
        "planSection": task_id.lower(),
        "status": status,
        "currentStep": "",
        "nextAction": "",
        "ownerRole": owner_by_status[status],
        "dependsOn": [],
        "files": {"create": [], "modify": ["src/feature.txt"], "test": []},
        "acceptance": ["Task acceptance is met"],
        "verification": {
            "commands": ["python3 .harness/tests/test_commit_task.py"],
            "checks": [],
            "lastResult": "passed" if status == "done" else "not_run",
        },
        "review": review_fixture(review_result),
        "blockedReason": "",
    }


def workflow_state(active_task_id: str | None = "TASK-002") -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-plan-001-v1",
        "activePlanRef": "./plans/active/PLAN-001/plan.md",
        "activeTaskId": active_task_id,
        "workflowStatus": "active",
        "currentPhase": "implementing" if active_task_id else "archiving",
        "ownerRole": "developer",
        "nextAction": "执行 TASK-002" if active_task_id else "归档当前 plan package",
        "updatedAt": "2026-04-27T09:00:00+08:00",
    }


class CommitTaskTest(unittest.TestCase):
    def init_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, text=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Harness Test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "harness-test@example.invalid"], cwd=root, check=True)
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "初始化测试仓库"], cwd=root, check=True, text=True, capture_output=True)

    def write_active_plan(self, root: Path, tasks: list[dict], state: dict | None = None) -> Path:
        plan_dir = root / "work" / "plans" / "active" / "PLAN-001"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text("# PLAN-001\n", encoding="utf-8")
        (plan_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "$schema": "../../../../.harness/schemas/tasks.schema.json",
                    "planId": "PLAN-001",
                    "planRef": "./plan.md",
                    "tasks": tasks,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        state_path = root / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state or workflow_state(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return plan_dir

    def run_commit_task(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
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

    def git(self, root: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True)
        return result.stdout.strip()

    def test_commits_done_task_and_allows_next_task_activation_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            self.write_active_plan(
                root,
                [
                    task_fixture("TASK-001", "Add commit gate", status="done"),
                    task_fixture("TASK-002", "Continue workflow", status="implementing"),
                ],
                workflow_state(active_task_id="TASK-002"),
            )
            source_path = root / "src" / "feature.txt"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("implemented\n", encoding="utf-8")

            result = self.run_commit_task(root, "--task", "TASK-001")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["action"], "commit-task")
            self.assertEqual(payload["taskId"], "TASK-001")
            self.assertEqual(payload["message"], "完成 TASK-001: Add commit gate")
            self.assertIn("work/workflow-state.json", payload["paths"])
            self.assertIn("work/plans/active/PLAN-001/tasks.json", payload["paths"])
            self.assertIn("src/feature.txt", payload["paths"])
            self.assertEqual(self.git(root, "log", "-1", "--pretty=%s"), "完成 TASK-001: Add commit gate")
            self.assertEqual(self.git(root, "status", "--porcelain"), "")

    def test_rejects_task_that_is_not_done_without_creating_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            self.write_active_plan(
                root,
                [task_fixture("TASK-001", "Add commit gate", status="reviewing")],
                workflow_state(active_task_id="TASK-001"),
            )
            (root / "src").mkdir()
            (root / "src" / "feature.txt").write_text("implemented\n", encoding="utf-8")
            before_head = self.git(root, "rev-parse", "HEAD")

            result = self.run_commit_task(root, "--task", "TASK-001")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("status 不是 done", result.stderr + result.stdout)
            self.assertEqual(self.git(root, "rev-parse", "HEAD"), before_head)

    def test_rejects_empty_worktree_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            self.write_active_plan(root, [task_fixture("TASK-001", "Add commit gate", status="done")])
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "准备已完成任务"], cwd=root, check=True, text=True, capture_output=True)

            result = self.run_commit_task(root, "--task", "TASK-001")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("没有可提交的变更", result.stderr + result.stdout)

    def test_reports_paths_when_changes_are_already_staged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            self.write_active_plan(root, [task_fixture("TASK-001", "Add commit gate", status="done")])
            source_path = root / "src" / "feature.txt"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("implemented\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)

            result = self.run_commit_task(root, "--task", "TASK-001")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertIn("src/feature.txt", payload["paths"])
            self.assertIn("work/plans/active/PLAN-001/tasks.json", payload["paths"])


if __name__ == "__main__":
    unittest.main()
