#!/usr/bin/env python3

from __future__ import annotations

import json
import importlib.util
import argparse
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "backlog-consume.py"


def load_backlog_consume_module():
    spec = importlib.util.spec_from_file_location("backlog_consume_script", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def backlog_item(item_id: str = "BL-001", source_ref: str = "chat:2026-04-28-001") -> dict:
    return {
        "id": item_id,
        "title": "Implement backlog consumption",
        "summary": "Remove consumed items from the pending backlog queue with audit evidence.",
        "dispatch": "queue",
        "sourceRef": source_ref,
        "createdAt": "2026-04-28T12:00:00+08:00",
    }


def task_manifest() -> dict:
    return {
        "$schema": "../../../../.harness/schemas/tasks.schema.json",
        "planId": "PLAN-123",
        "planRef": "./plan.md",
        "tasks": [
            {
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
                    "commands": ["python3 -m unittest"],
                    "checks": [],
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
        ],
    }


class BacklogConsumeTest(unittest.TestCase):
    def write_harness_assets(self, root: Path) -> None:
        for relative in (
            ".harness/schemas/backlogs.schema.json",
            ".harness/schemas/backlog-consumption-event.schema.json",
            ".harness/schemas/tasks.schema.json",
            ".harness/schemas/workflow-state.schema.json",
            ".harness/scripts/validate-state.py",
        ):
            source = REPO_ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def write_store(self, root: Path, *, items: list[dict] | None = None, next_id: int = 3) -> Path:
        store_path = root / "work" / "backlog" / "backlogs.json"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text(
            json.dumps(
                {
                    "$schema": "../../.harness/schemas/backlogs.schema.json",
                    "nextId": next_id,
                    "items": items if items is not None else [backlog_item(), backlog_item("BL-002", "chat:2026-04-28-002")],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return store_path

    def write_plan_target(self, root: Path, *, include_reference: bool = True) -> Path:
        plan_dir = root / "work" / "plans" / "active" / "PLAN-123"
        plan_dir.mkdir(parents=True, exist_ok=True)
        source_line = "Source backlog: BL-001 / chat:2026-04-28-001" if include_reference else "Source backlog: none"
        (plan_dir / "plan.md").write_text(
            "\n".join(
                [
                    "# PLAN-123: Consume backlog item",
                    "",
                    source_line,
                    "",
                    "## Plan Review Gate",
                    "",
                    "Status: passed",
                    "Reviewer: test",
                    "Reviewed At: 2026-04-28T12:05:00+08:00",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (plan_dir / "tasks.json").write_text(
            json.dumps(task_manifest(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (plan_dir / "handoff.md").write_text("# Handoff\n\nSource backlog: BL-001\n", encoding="utf-8")
        return plan_dir

    def write_direct_state(self, root: Path, workflow_id: str = "workflow-direct-20260428-v1") -> Path:
        state_path = root / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "$schema": "../.harness/schemas/workflow-state.schema.json",
                    "workflowId": workflow_id,
                    "activePlanRef": None,
                    "activeTaskId": None,
                    "workflowStatus": "active",
                    "currentPhase": "implementing",
                    "ownerRole": "developer",
                    "nextAction": "Execute backlog source work",
                    "updatedAt": "2026-04-28T12:10:00+08:00",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return state_path

    def run_consume(
        self,
        root: Path,
        *,
        item_id: str = "BL-001",
        target_ref: str = "plan:PLAN-123",
        reason: str = "Converted into downstream Harness artifact.",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                "--id",
                item_id,
                "--target-ref",
                target_ref,
                "--reason",
                reason,
                "--consumed-at",
                "2026-04-28T12:30:00+08:00",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def read_store(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def read_events(self, root: Path) -> list[dict]:
        event_path = root / "work" / "backlog" / "consumed.jsonl"
        return [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]

    def assert_event_schema_valid(self, root: Path, event: dict) -> None:
        schema = json.loads((root / ".harness" / "schemas" / "backlog-consumption-event.schema.json").read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema).iter_errors(event), key=lambda err: list(err.absolute_path))
        self.assertEqual(errors, [])

    def test_plan_target_consumption_removes_item_and_appends_schema_valid_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = self.write_store(root)
            self.write_plan_target(root)

            result = self.run_consume(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            store = self.read_store(store_path)
            self.assertEqual(store["nextId"], 3)
            self.assertEqual([item["id"] for item in store["items"]], ["BL-002"])
            events = self.read_events(root)
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assert_event_schema_valid(root, event)
            self.assertEqual(event["eventType"], "backlog.consumed")
            self.assertEqual(event["backlogId"], "BL-001")
            self.assertEqual(event["targetRef"], "plan:PLAN-123")
            self.assertEqual(event["item"]["sourceRef"], "chat:2026-04-28-001")
            self.assertIn('"status": "consumed"', result.stdout)

    def test_rejects_unknown_backlog_id_and_preserves_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = self.write_store(root)
            original = store_path.read_text(encoding="utf-8")
            self.write_plan_target(root)

            result = self.run_consume(root, item_id="BL-999")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("unknown backlog id", result.stderr + result.stdout)
            self.assertEqual(store_path.read_text(encoding="utf-8"), original)
            self.assertFalse((root / "work" / "backlog" / "consumed.jsonl").exists())

    def test_rejects_malformed_target_ref_and_preserves_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = self.write_store(root)
            original = store_path.read_text(encoding="utf-8")

            result = self.run_consume(root, target_ref="PLAN-123")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("targetRef", result.stderr + result.stdout)
            self.assertEqual(store_path.read_text(encoding="utf-8"), original)
            self.assertFalse((root / "work" / "backlog" / "consumed.jsonl").exists())

    def test_rejects_plan_target_without_downstream_backlog_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = self.write_store(root)
            original = store_path.read_text(encoding="utf-8")
            self.write_plan_target(root, include_reference=False)
            (root / "work" / "plans" / "active" / "PLAN-123" / "handoff.md").write_text(
                "# Handoff\n\nNo backlog source.\n",
                encoding="utf-8",
            )

            result = self.run_consume(root)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("does not reference backlog source", result.stderr + result.stdout)
            self.assertEqual(store_path.read_text(encoding="utf-8"), original)
            self.assertFalse((root / "work" / "backlog" / "consumed.jsonl").exists())

    def test_workflow_target_requires_matching_state_and_session_source_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = self.write_store(root, items=[backlog_item()], next_id=2)
            self.write_direct_state(root)

            missing_audit = self.run_consume(root, target_ref="workflow:workflow-direct-20260428-v1")

            self.assertEqual(missing_audit.returncode, 1, missing_audit.stderr + missing_audit.stdout)
            self.assertIn("session audit", missing_audit.stderr + missing_audit.stdout)
            self.assertEqual([item["id"] for item in self.read_store(store_path)["items"]], ["BL-001"])

            session_dir = root / "work" / "sessions" / "2026-04-28"
            session_dir.mkdir(parents=True)
            (session_dir / "session-direct.md").write_text(
                "Direct workflow source: BL-001 / chat:2026-04-28-001\n",
                encoding="utf-8",
            )

            result = self.run_consume(root, target_ref="workflow:workflow-direct-20260428-v1")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(self.read_store(store_path)["items"], [])
            event = self.read_events(root)[0]
            self.assert_event_schema_valid(root, event)
            self.assertEqual(event["targetRef"], "workflow:workflow-direct-20260428-v1")

    def test_rolls_back_consumed_event_when_store_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = self.write_store(root)
            original_store = store_path.read_text(encoding="utf-8")
            self.write_plan_target(root)
            module = load_backlog_consume_module()
            original_writer = module.atomic_write_json

            def failing_store_write(path: Path, data: dict) -> None:
                if path == root / "work" / "backlog" / "backlogs.json":
                    raise OSError("simulated store write failure")
                original_writer(path, data)

            module.atomic_write_json = failing_store_write
            args = argparse.Namespace(
                root=root,
                id="BL-001",
                target_ref="plan:PLAN-123",
                reason="Converted into downstream Harness artifact.",
                consumed_at="2026-04-28T12:30:00+08:00",
            )

            with self.assertRaises(module.BacklogConsumeError):
                module.consume(root, args)

            self.assertEqual(store_path.read_text(encoding="utf-8"), original_store)
            self.assertFalse((root / "work" / "backlog" / "consumed.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
