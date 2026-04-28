#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_DOC = REPO_ROOT / "installer" / "install-lifecycle.md"
HARNESS_INSTALL_RULE = REPO_ROOT / ".harness" / "rules" / "install-rules.md"
ARCHITECTURE = REPO_ROOT / ".harness" / "ARCHITECTURE.md"
README = REPO_ROOT / "README.md"
AGENTS = REPO_ROOT / "AGENTS.md"
MANAGED_BLOCK_TEMPLATE = REPO_ROOT / ".harness" / "templates" / "entrypoint-managed-block.template.md"
PROJECT_INIT_SKILL = REPO_ROOT / ".harness" / "skills" / "project-init" / "SKILL.md"
SESSION_START = REPO_ROOT / ".harness" / "scripts" / "session-start.py"


class InstallerBoundaryTest(unittest.TestCase):
    def test_installer_lifecycle_lives_outside_harness_runtime_core(self) -> None:
        self.assertTrue(INSTALL_DOC.exists(), "installer lifecycle belongs in installer/install-lifecycle.md")
        self.assertFalse(HARNESS_INSTALL_RULE.exists(), "installer lifecycle must not be a .harness runtime rule")

    def test_runtime_entrypoints_do_not_reference_harness_install_rule_asset(self) -> None:
        paths = (
            ARCHITECTURE,
            README,
            AGENTS,
            MANAGED_BLOCK_TEMPLATE,
            PROJECT_INIT_SKILL,
        )

        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn(".harness/rules/install-rules.md", text)

    def test_session_start_required_assets_exclude_installer_lifecycle(self) -> None:
        text = SESSION_START.read_text(encoding="utf-8")

        self.assertNotIn(".harness/rules/install-rules.md", text)


if __name__ == "__main__":
    unittest.main()
