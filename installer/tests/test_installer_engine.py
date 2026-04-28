#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from harness_engineering_installer.installer import (  # noqa: E402
    InstallMode,
    check_harness,
    install_harness,
)


class InstallerEngineTest(unittest.TestCase):
    def test_dry_run_reports_operations_without_writing_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()

            result = install_harness(target, dry_run=True)

            self.assertGreater(result.copy_count, 0)
            self.assertEqual(result.prune_count, 0)
            self.assertFalse((target / ".harness").exists())
            self.assertTrue(any(op.action == "copy" for op in result.operations))

    def test_install_copies_fixed_assets_only_and_preserves_runtime_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            (target / "work").mkdir()
            (target / "work" / "workflow-state.json").write_text("runtime-state\n", encoding="utf-8")
            (target / ".harness" / "contracts").mkdir(parents=True)
            (target / ".harness" / "contracts" / "project-contracts.json").write_text(
                "project-contract\n",
                encoding="utf-8",
            )
            for root_file in ("AGENTS.md", "README.md", "ARCHITECTURE.md"):
                (target / root_file).write_text(f"{root_file} original\n", encoding="utf-8")

            result = install_harness(target)

            self.assertGreater(result.copy_count, 0)
            self.assertTrue((target / ".harness" / "ARCHITECTURE.md").is_file())
            self.assertTrue((target / ".harness" / "scripts" / "harness").is_file())
            self.assertEqual((target / "work" / "workflow-state.json").read_text(encoding="utf-8"), "runtime-state\n")
            self.assertEqual(
                (target / ".harness" / "contracts" / "project-contracts.json").read_text(encoding="utf-8"),
                "project-contract\n",
            )
            for root_file in ("AGENTS.md", "README.md", "ARCHITECTURE.md"):
                self.assertEqual(
                    (target / root_file).read_text(encoding="utf-8"),
                    f"{root_file} original\n",
                )

    def test_update_prunes_only_manifest_retired_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            retired = target / ".harness" / "rules" / "install-rules.md"
            unrelated = target / ".harness" / "rules" / "custom-user-rule.md"
            retired.parent.mkdir(parents=True)
            retired.write_text("old install rules\n", encoding="utf-8")
            unrelated.write_text("keep me\n", encoding="utf-8")

            result = install_harness(target, mode=InstallMode.UPDATE)

            self.assertGreaterEqual(result.prune_count, 1)
            self.assertFalse(retired.exists())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me\n")

    def test_check_reports_missing_assets_without_mutating_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()

            report = check_harness(target)

            self.assertFalse(report.ok)
            self.assertIn(".harness/ARCHITECTURE.md", report.missing_assets)
            self.assertFalse((target / ".harness").exists())


if __name__ == "__main__":
    unittest.main()
