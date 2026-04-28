#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_DOC = REPO_ROOT / "installer" / "install-lifecycle.md"


class InstallLifecycleTest(unittest.TestCase):
    def read_doc(self) -> str:
        return INSTALL_DOC.read_text(encoding="utf-8")

    def test_install_lifecycle_documents_ordered_handoff(self) -> None:
        text = self.read_doc()

        anchors = [
            "1. Release fixed Harness assets",
            "2. Run installer self-checks",
            "3. Hand off to `project-init`",
            "4. Hand off to `project-env-contract`",
            "5. Enter normal Harness workflow",
        ]
        positions = [text.index(anchor) for anchor in anchors]
        self.assertEqual(positions, sorted(positions))

    def test_install_lifecycle_keeps_installer_outside_runtime_state(self) -> None:
        text = self.read_doc()

        self.assertIn("must not write `work/workflow-state.json`", text)
        self.assertIn("must not write `tasks.json`", text)
        self.assertIn("must not create active plan packages", text)
        self.assertIn("must preserve existing `.harness/contracts/` and `work/`", text)

    def test_install_lifecycle_points_to_runtime_onboarding_without_owning_it(self) -> None:
        text = self.read_doc()

        self.assertIn("`.harness/skills/project-init/SKILL.md`", text)
        self.assertIn("`.harness/skills/project-env-contract/SKILL.md`", text)
        self.assertIn("`session-start.py`", text)
        self.assertIn("`check-project-env.py`", text)
        self.assertIn("The installer does not become a Harness workflow gate", text)

    def test_install_lifecycle_documents_distribution_path(self) -> None:
        text = self.read_doc()

        self.assertIn("pipx install harness-engineering", text)
        self.assertIn("uv tool install harness-engineering", text)
        self.assertIn("PyPI publishing and release workflow are future release tasks", text)


if __name__ == "__main__":
    unittest.main()
