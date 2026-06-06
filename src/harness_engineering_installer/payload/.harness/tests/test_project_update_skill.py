#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / ".harness" / "skills" / "project-update" / "SKILL.md"
PROJECT_INIT = REPO_ROOT / ".harness" / "skills" / "project-init" / "SKILL.md"
HARNESS_ARCHITECTURE = REPO_ROOT / ".harness" / "ARCHITECTURE.md"


class ProjectUpdateSkillTest(unittest.TestCase):
    def read_skill(self) -> str:
        return SKILL.read_text(encoding="utf-8")

    def test_frontmatter_identifies_project_update_skill(self) -> None:
        text = self.read_skill()

        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: project-update", text)
        self.assertIn("description:", text)
        self.assertIn("already-onboarded", text)
        self.assertIn("target project", text)
        self.assertNotIn("name: project-init", text)

    def test_requires_installer_update_before_semantic_sync(self) -> None:
        text = self.read_skill()

        self.assertIn("hally-harness-engineering update", text)
        self.assertIn("fixed `.harness/` assets", text)
        self.assertIn("must already be present", text)
        self.assertIn("Do not copy fixed assets manually", text)
        self.assertIn("HARNESS_ASSETS_MISSING", text)

    def test_limits_entrypoint_writes_to_managed_block(self) -> None:
        text = self.read_skill()

        self.assertIn("init-project-entrypoint.py --write", text)
        self.assertIn("only the Harness managed block", text)
        self.assertIn("Do not rewrite user-owned prose outside the managed block", text)
        self.assertIn("marker-outside recommendation", text)

    def test_keeps_semantic_judgment_with_llm_not_scripts(self) -> None:
        text = self.read_skill()

        self.assertIn("semantic conflict judgment belongs to the Agent", text)
        self.assertIn("deterministic scripts must not infer intent", text)
        self.assertIn("report conflicts before changing user-owned prose", text)

    def test_preserves_runtime_and_project_contract_boundaries(self) -> None:
        text = self.read_skill()

        self.assertIn("Do not write `workflow-state.json`", text)
        self.assertIn("Do not write `tasks.json`", text)
        self.assertIn("must not overwrite `.harness/contracts/project-contracts.json`", text)
        self.assertIn("delegate to `project-env-contract`", text)

    def test_project_init_points_existing_projects_to_project_update(self) -> None:
        text = PROJECT_INIT.read_text(encoding="utf-8")

        self.assertIn("project-update", text)
        self.assertIn("already-onboarded", text)
        self.assertIn("after installer update", text)

    def test_architecture_documents_project_update_boundary(self) -> None:
        text = HARNESS_ARCHITECTURE.read_text(encoding="utf-8")

        self.assertIn(".harness/skills/project-update/SKILL.md", text)
        self.assertIn("already-onboarded target repositories", text)
        self.assertIn("installer update owns fixed asset copying", text)
        self.assertIn("managed block synchronization", text)


if __name__ == "__main__":
    unittest.main()
