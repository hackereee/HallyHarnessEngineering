#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "init-project-entrypoint.py"
SCHEMA = REPO_ROOT / ".harness" / "schemas" / "project-entrypoints.schema.json"


class InitProjectEntrypointTest(unittest.TestCase):
    def run_script(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                "--schema",
                str(SCHEMA),
                *args,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_detect_reports_existing_entrypoints_in_priority_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
            cursor_rule = root / ".cursor" / "rules" / "style.mdc"
            cursor_rule.parent.mkdir(parents=True)
            cursor_rule.write_text("rule", encoding="utf-8")

            result = self.run_script(root, "--detect")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(result.stdout)
            self.assertEqual(data["canonicalEntry"], "AGENTS.md")
            self.assertEqual(data["managedBlockVersion"], "harness-entrypoint-block-v1")
            self.assertEqual(data["projectArchitectureRef"], "ARCHITECTURE.md")
            self.assertEqual(data["harnessArchitectureRef"], ".harness/ARCHITECTURE.md")
            self.assertEqual(
                [entry["path"] for entry in data["detectedEntries"]],
                ["AGENTS.md", "CLAUDE.md", ".cursor/rules/style.mdc"],
            )
            self.assertEqual(data["detectedEntries"][0]["harnessBlockVersion"], None)

    def test_detect_reports_legacy_managed_block_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Agents\n\n"
                "<!-- harness-engineering:start -->\n"
                "old block without version\n"
                "<!-- harness-engineering:end -->\n",
                encoding="utf-8",
            )

            result = self.run_script(root, "--detect")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(result.stdout)
            self.assertEqual(data["detectedEntries"][0]["harnessBlock"], "present")
            self.assertEqual(data["detectedEntries"][0]["harnessBlockVersion"], "legacy")

    def test_detect_without_entrypoints_returns_needs_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = self.run_script(root, "--detect")

            self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
            self.assertIn("NEEDS_ENTRYPOINT", result.stdout)
            self.assertIn("AGENTS.md", result.stdout)

    def test_write_updates_only_managed_block_and_writes_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = root / "AGENTS.md"
            entry.write_text(
                "# Agents\n\n"
                "Keep this rule.\n\n"
                "<!-- harness-engineering:start -->\n"
                "old block\n"
                "<!-- harness-engineering:end -->\n\n"
                "Keep this footer.\n",
                encoding="utf-8",
            )

            result = self.run_script(root, "--write", "--entry", "AGENTS.md")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            text = entry.read_text(encoding="utf-8")
            self.assertIn("Keep this rule.", text)
            self.assertIn("Keep this footer.", text)
            self.assertNotIn("old block", text)
            self.assertEqual(text.count("<!-- harness-engineering:start -->"), 1)
            self.assertEqual(text.count("<!-- harness-engineering:end -->"), 1)
            self.assertIn("Managed block version: `harness-entrypoint-block-v1`", text)
            self.assertIn("Conflict priority:", text)
            self.assertIn("tests map to the `testing` gate", text)
            self.assertIn("reviews map to the `reviewing` gate", text)
            self.assertIn("Write gateways:", text)
            self.assertIn("Task modeling:", text)
            self.assertIn(".harness/ARCHITECTURE.md", text)
            self.assertIn("ARCHITECTURE.md", text)
            self.assertIn("work/workflow-state.json", text)

            contract = json.loads(
                (root / ".harness" / "contracts" / "project-entrypoints.json").read_text(encoding="utf-8")
            )
            self.assertEqual(contract["canonicalEntry"], "AGENTS.md")
            self.assertEqual(contract["managedBlockVersion"], "harness-entrypoint-block-v1")
            self.assertEqual(contract["projectArchitectureRef"], "ARCHITECTURE.md")
            self.assertEqual(contract["detectedEntries"][0]["harnessBlock"], "present")
            self.assertEqual(contract["detectedEntries"][0]["harnessBlockVersion"], "harness-entrypoint-block-v1")
            self.assertTrue((root / "ARCHITECTURE.md").exists())
            self.assertEqual((root / "ARCHITECTURE.md").read_text(encoding="utf-8"), "")

    def test_write_is_idempotent_for_current_managed_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = root / "AGENTS.md"
            entry.write_text("# Agents\n\nKeep this rule.\n", encoding="utf-8")

            first = self.run_script(root, "--write", "--entry", "AGENTS.md")
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            first_text = entry.read_text(encoding="utf-8")
            first_contract = (root / ".harness" / "contracts" / "project-entrypoints.json").read_text(
                encoding="utf-8"
            )

            second = self.run_script(root, "--write", "--entry", "AGENTS.md")

            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertEqual(entry.read_text(encoding="utf-8"), first_text)
            self.assertEqual(
                (root / ".harness" / "contracts" / "project-entrypoints.json").read_text(encoding="utf-8"),
                first_contract,
            )
            self.assertEqual(first_text.count("<!-- harness-engineering:start -->"), 1)
            self.assertEqual(first_text.count("<!-- harness-engineering:end -->"), 1)

    def test_create_entrypoint_writes_file_and_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = self.run_script(root, "--create", "AGENTS.md")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / "ARCHITECTURE.md").exists())
            self.assertTrue((root / ".harness" / "contracts" / "project-entrypoints.json").exists())
            self.assertIn("CREATED AGENTS.md", result.stdout)

    def test_write_preserves_existing_project_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
            (root / "ARCHITECTURE.md").write_text("# Project\n\nExisting architecture.\n", encoding="utf-8")

            result = self.run_script(root, "--write", "--entry", "AGENTS.md")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(
                (root / "ARCHITECTURE.md").read_text(encoding="utf-8"),
                "# Project\n\nExisting architecture.\n",
            )

    def test_write_missing_entrypoint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = self.run_script(root, "--write", "--entry", "AGENTS.md")

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("entrypoint not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
