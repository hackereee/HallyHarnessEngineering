#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / ".harness" / "skills" / "project-init" / "SKILL.md"
HARNESS_ARCHITECTURE = REPO_ROOT / ".harness" / "ARCHITECTURE.md"
LEGACY_ARCHITECTURE = REPO_ROOT / "harness-design" / "architecture.md"


class ProjectInitSkillTest(unittest.TestCase):
    def read_skill(self) -> str:
        return SKILL.read_text(encoding="utf-8")

    def test_frontmatter_identifies_project_init_skill(self) -> None:
        text = self.read_skill()

        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: project-init", text)
        self.assertIn("description:", text)
        self.assertIn("real project", text)
        self.assertIn("agent entrypoint", text)

    def test_detects_agent_entrypoints_before_writing_references(self) -> None:
        text = self.read_skill()

        detect_index = text.index("## Entrypoint Detection")
        write_index = text.index("## Managed Block Update")
        self.assertLess(detect_index, write_index)
        self.assertIn("AGENTS.md", text)
        self.assertIn("CLAUDE.md", text)
        self.assertIn("GEMINI.md", text)
        self.assertIn(".github/copilot-instructions.md", text)

    def test_recommends_agents_md_when_no_entrypoint_exists(self) -> None:
        text = self.read_skill()

        self.assertIn("NEEDS_ENTRYPOINT", text)
        self.assertIn("recommend creating `AGENTS.md`", text)
        self.assertIn("unless the user explicitly chooses another entrypoint", text)

    def test_uses_stable_harness_architecture_reference(self) -> None:
        text = self.read_skill()

        self.assertIn(".harness/ARCHITECTURE.md", text)
        self.assertIn("root `ARCHITECTURE.md`", text)
        self.assertIn("business architecture", text)
        self.assertIn("Harness framework architecture", text)

    def test_requires_root_architecture_file_for_future_updates(self) -> None:
        text = self.read_skill()

        self.assertIn("ensure root `ARCHITECTURE.md` exists", text)
        self.assertIn("create an empty root `ARCHITECTURE.md`", text)
        self.assertIn("future task completion summaries", text)

    def test_delegates_environment_contract_to_project_env_contract(self) -> None:
        text = self.read_skill()

        self.assertIn("project-env-contract", text)
        self.assertIn(".harness/contracts/project-contracts.json", text)
        self.assertNotIn("Write project contracts before custom scripts or adapters.", text)

    def test_architecture_documents_project_init_skill_boundary(self) -> None:
        text = HARNESS_ARCHITECTURE.read_text(encoding="utf-8")

        self.assertIn(".harness/skills/project-init/SKILL.md", text)
        self.assertIn(".harness/skills/project-env-contract/SKILL.md", text)
        self.assertIn(".harness/ARCHITECTURE.md", text)
        self.assertIn("root `ARCHITECTURE.md`", text)
        self.assertIn("业务架构", text)

    def test_harness_architecture_doc_exists(self) -> None:
        text = HARNESS_ARCHITECTURE.read_text(encoding="utf-8")

        self.assertIn("# Harness Framework Architecture", text)
        self.assertIn(".harness/", text)
        self.assertIn("work/", text)

    def test_legacy_harness_design_architecture_is_removed(self) -> None:
        self.assertFalse(LEGACY_ARCHITECTURE.exists())


if __name__ == "__main__":
    unittest.main()
