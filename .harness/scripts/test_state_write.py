#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_WRITE = REPO_ROOT / ".harness" / "scripts" / "state-write.py"
VALIDATOR = REPO_ROOT / ".harness" / "scripts" / "validate-state.py"
STATE_SCHEMA = REPO_ROOT / ".harness" / "schemas" / "workflow-state.schema.json"


def base_state() -> dict:
    return {
        "$schema": "../.harness/schemas/workflow-state.schema.json",
        "workflowId": "workflow-fix-login-20260425-v1",
        "activePlanRef": None,
        "activeTaskId": None,
        "workflowStatus": "active",
        "currentPhase": "implementing",
        "ownerRole": "developer",
        "nextAction": "Run login regression test",
        "updatedAt": "2026-04-25T20:00:00+08:00",
    }


class StateWriteTest(unittest.TestCase):
    def write_state(self, tmp: str) -> Path:
        state_path = Path(tmp) / "work" / "workflow-state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(base_state(), indent=2) + "\n", encoding="utf-8")
        return state_path

    def run_state_write(self, state_path: Path, patch: list[dict]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(STATE_WRITE),
                "--state",
                str(state_path),
                "--schema",
                str(STATE_SCHEMA),
                "--validator",
                str(VALIDATOR),
                "--patch-json",
                json.dumps(patch),
                "--source",
                "test_state_write.py",
                "--reason",
                "verify phase ownerRole warning",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_phase_change_without_owner_role_patch_is_rejected_by_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_state(tmp)
            patch = [
                {"op": "replace", "path": "/currentPhase", "value": "testing"},
                {"op": "replace", "path": "/nextAction", "value": "Run verification command"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("'tester' was expected", result.stderr + result.stdout)

            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["currentPhase"], "implementing")

    def test_phase_change_with_owner_role_patch_does_not_warn_about_owner_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_state(tmp)
            patch = [
                {"op": "replace", "path": "/currentPhase", "value": "testing"},
                {"op": "replace", "path": "/ownerRole", "value": "tester"},
                {"op": "replace", "path": "/nextAction", "value": "Run verification command"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertNotIn("ownerRole 未显式刷新", result.stderr)

    def test_rejects_illegal_phase_jump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self.write_state(tmp)
            patch = [
                {"op": "replace", "path": "/currentPhase", "value": "reviewing"},
                {"op": "replace", "path": "/ownerRole", "value": "reviewer"},
                {"op": "replace", "path": "/nextAction", "value": "Review implementation"},
            ]

            result = self.run_state_write(state_path, patch)

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("非法阶段流转", result.stderr + result.stdout)

            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["currentPhase"], "implementing")


if __name__ == "__main__":
    unittest.main()
