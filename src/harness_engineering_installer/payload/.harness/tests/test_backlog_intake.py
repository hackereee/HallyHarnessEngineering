#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "backlog-intake.py"


class BacklogIntakeTest(unittest.TestCase):
    def write_harness_assets(self, root: Path) -> None:
        for relative in (
            ".harness/schemas/backlogs.schema.json",
            ".harness/templates/backlogs.template.json",
        ):
            source = REPO_ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def run_intake(
        self,
        root: Path,
        *,
        title: str = "Add backlog intake",
        summary: str = "Record incoming work without mutating the active workflow.",
        dispatch: str = "queue",
        source_ref: str = "chat:2026-04-27-001",
        created_at: str | None = "2026-04-27T10:00:00+08:00",
        notes: str | None = "Initial intake item.",
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(root),
            "--title",
            title,
            "--summary",
            summary,
            "--dispatch",
            dispatch,
            "--source-ref",
            source_ref,
        ]
        if created_at is not None:
            command += ["--created-at", created_at]
        if notes is not None:
            command += ["--notes", notes]
        return subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)

    def test_creates_store_from_template_and_appends_first_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            result = self.run_intake(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            store_path = root / "work" / "backlog" / "backlogs.json"
            self.assertTrue(store_path.exists())
            store = json.loads(store_path.read_text(encoding="utf-8"))
            self.assertEqual(store["$schema"], "../../.harness/schemas/backlogs.schema.json")
            self.assertEqual(store["nextId"], 2)
            self.assertEqual(len(store["items"]), 1)
            self.assertEqual(
                store["items"][0],
                {
                    "id": "BL-001",
                    "title": "Add backlog intake",
                    "summary": "Record incoming work without mutating the active workflow.",
                    "dispatch": "queue",
                    "sourceRef": "chat:2026-04-27-001",
                    "createdAt": "2026-04-27T10:00:00+08:00",
                    "notes": "Initial intake item.",
                },
            )
            self.assertIn('"id": "BL-001"', result.stdout)
            self.assertIn('"dispatch": "queue"', result.stdout)

    def test_repeated_intake_allocates_sequential_ids_and_preserves_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)

            first = self.run_intake(root, source_ref="chat:2026-04-27-001")
            second = self.run_intake(
                root,
                title="Urgent production issue",
                summary="Evaluate whether the current workflow should be interrupted.",
                dispatch="preempt",
                source_ref="issue:123",
                created_at="2026-04-27T10:05:00+08:00",
                notes=None,
            )

            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            store = json.loads((root / "work" / "backlog" / "backlogs.json").read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in store["items"]], ["BL-001", "BL-002"])
            self.assertEqual(store["nextId"], 3)
            self.assertEqual(store["items"][0]["sourceRef"], "chat:2026-04-27-001")
            self.assertEqual(store["items"][1]["dispatch"], "preempt")
            self.assertNotIn("notes", store["items"][1])

    def test_existing_store_without_next_id_migrates_to_max_existing_id_plus_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = root / "work" / "backlog" / "backlogs.json"
            store_path.parent.mkdir(parents=True)
            store_path.write_text(
                json.dumps(
                    {
                        "$schema": "../../.harness/schemas/backlogs.schema.json",
                        "items": [
                            {
                                "id": "BL-005",
                                "title": "Existing item",
                                "summary": "A pre-nextId pending item.",
                                "dispatch": "queue",
                                "sourceRef": "chat:2026-04-27-005",
                                "createdAt": "2026-04-27T09:00:00+08:00",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_intake(root, source_ref="chat:2026-04-27-006")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            store = json.loads(store_path.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in store["items"]], ["BL-005", "BL-006"])
            self.assertEqual(store["nextId"], 7)

    def test_intake_allocates_from_next_id_without_reusing_removed_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = root / "work" / "backlog" / "backlogs.json"
            store_path.parent.mkdir(parents=True)
            store_path.write_text(
                json.dumps(
                    {
                        "$schema": "../../.harness/schemas/backlogs.schema.json",
                        "nextId": 7,
                        "items": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_intake(root, source_ref="chat:2026-04-27-007")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            store = json.loads(store_path.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in store["items"]], ["BL-007"])
            self.assertEqual(store["nextId"], 8)

    def test_invalid_existing_store_blocks_write_and_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            store_path = root / "work" / "backlog" / "backlogs.json"
            store_path.parent.mkdir(parents=True)
            invalid_store = {
                "$schema": "../.harness/schemas/backlogs.schema.json",
                "nextId": 3,
                "items": [
                    {
                        "id": "BL-001",
                        "title": "Existing item",
                        "summary": "Already queued work.",
                        "dispatch": "queue",
                        "sourceRef": "chat:2026-04-27-001",
                        "createdAt": "2026-04-27T09:00:00+08:00",
                    },
                    {
                        "id": "BL-001",
                        "title": "Duplicate item",
                        "summary": "This duplicate should block intake.",
                        "dispatch": "queue",
                        "sourceRef": "chat:2026-04-27-002",
                        "createdAt": "2026-04-27T09:05:00+08:00",
                    },
                ],
            }
            original_text = json.dumps(invalid_store, ensure_ascii=False, indent=2) + "\n"
            store_path.write_text(original_text, encoding="utf-8")

            result = self.run_intake(root, source_ref="chat:2026-04-27-003")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("backlogs.json validation failed", result.stderr + result.stdout)
            self.assertEqual(store_path.read_text(encoding="utf-8"), original_text)

    def test_intake_does_not_mutate_workflow_state_tasks_or_active_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_harness_assets(root)
            state_path = root / "work" / "workflow-state.json"
            tasks_path = root / "work" / "plans" / "active" / "PLAN-001" / "tasks.json"
            plan_path = tasks_path.with_name("plan.md")
            handoff_path = tasks_path.with_name("handoff.md")
            for path, text in (
                (state_path, '{"workflowId":"workflow-existing"}\n'),
                (tasks_path, '{"tasks":[]}\n'),
                (plan_path, "# Plan\n"),
                (handoff_path, "# Handoff\n"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            originals = {
                path: path.read_text(encoding="utf-8")
                for path in (state_path, tasks_path, plan_path, handoff_path)
            }

            result = self.run_intake(root)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            for path, original in originals.items():
                with self.subTest(path=path):
                    self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
