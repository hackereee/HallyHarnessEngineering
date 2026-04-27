#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / ".harness" / "skills" / "project-init" / "SKILL.md"
ARCHITECTURE = REPO_ROOT / "harness-design" / "architecture.md"
CONTRACTS_DIR = REPO_ROOT / ".harness" / "contracts"


class ProjectInitSkillTest(unittest.TestCase):
    def read_skill(self) -> str:
        return SKILL.read_text(encoding="utf-8")

    def test_frontmatter_identifies_project_init_skill(self) -> None:
        text = self.read_skill()

        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: project-init", text)
        self.assertIn("description:", text)
        self.assertIn("initializing Harness", text)
        self.assertIn("target development repository", text)

    def test_requires_repository_evidence_before_questions(self) -> None:
        text = self.read_skill()

        evidence_index = text.index("## Repository Evidence First")
        questions_index = text.index("## Blocking Questions")
        self.assertLess(evidence_index, questions_index)
        self.assertIn("Read repository evidence before asking user questions.", text)
        self.assertIn("Ask only questions that block a verifiable contract.", text)

    def test_separates_harness_core_from_project_environment(self) -> None:
        text = self.read_skill()

        self.assertIn("Harness core checks", text)
        self.assertIn("project environment checks", text)
        self.assertIn("Do not add project-specific checks to `session-start.py`.", text)
        self.assertIn("Do not write `workflow-state.json` directly.", text)

    def test_requires_contracts_before_scripts_or_adapters(self) -> None:
        text = self.read_skill()
        lowered = text.lower()

        self.assertIn("project profile", lowered)
        self.assertIn("environment checks", lowered)
        self.assertIn("command registry", lowered)
        self.assertIn("blocking", lowered)
        self.assertIn("warning", lowered)
        self.assertIn("adapter fallback", lowered)
        self.assertIn("Write project contracts before custom scripts or adapters.", text)
        self.assertIn(".harness/contracts/project-contracts.json", text)
        self.assertIn("check-project-env", text)
        self.assertIn("contracts are the truth source", lowered)

    def test_architecture_documents_project_init_skill_boundary(self) -> None:
        text = ARCHITECTURE.read_text(encoding="utf-8")

        self.assertIn(".harness/skills/project-init/SKILL.md", text)
        self.assertIn(".harness/schemas/project-contracts.schema.json", text)
        self.assertIn(".harness/scripts/check-project-env.py", text)
        self.assertIn("project environment differences belong in project contracts", text)
        self.assertIn("not in `session-start.py`", text)
        self.assertIn("`.harness/` 只写契约、模板、规则、技能与工具", text)

    def test_contracts_directory_exists_without_requiring_configured_contract(self) -> None:
        self.assertTrue(CONTRACTS_DIR.is_dir())
        self.assertFalse((CONTRACTS_DIR / "project-contracts.json").exists())

    def test_docs_state_project_contract_can_be_not_configured(self) -> None:
        architecture = ARCHITECTURE.read_text(encoding="utf-8")
        skill = self.read_skill()

        self.assertIn("project-contracts.json may be absent until project-init configures it", architecture)
        self.assertIn("NOT_CONFIGURED", architecture)
        self.assertIn("project-contracts.json may be absent until project-init configures it", skill)
        self.assertIn("NOT_CONFIGURED", skill)


if __name__ == "__main__":
    unittest.main()
