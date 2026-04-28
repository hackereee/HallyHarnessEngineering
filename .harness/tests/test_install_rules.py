#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_RULE = REPO_ROOT / ".harness" / "rules" / "install-rules.md"
ARCHITECTURE = REPO_ROOT / ".harness" / "ARCHITECTURE.md"
README = REPO_ROOT / "README.md"
AGENTS = REPO_ROOT / "AGENTS.md"
MANAGED_BLOCK_TEMPLATE = REPO_ROOT / ".harness" / "templates" / "entrypoint-managed-block.template.md"


class InstallRulesTest(unittest.TestCase):
    def read_rule(self) -> str:
        return INSTALL_RULE.read_text(encoding="utf-8")

    def test_install_rule_documents_ordered_lifecycle(self) -> None:
        text = self.read_rule()

        anchors = [
            "1. install-harness releases fixed `.harness/` assets",
            "2. Harness core self-check",
            "3. Agent runs `project-init`",
            "4. Agent runs `project-env-contract`",
            "5. Enter the actual workflow",
        ]
        positions = [text.index(anchor) for anchor in anchors]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("`init-project-entrypoint.py --write` or `--create`", text)
        self.assertIn("`.harness/contracts/project-contracts.json`", text)
        self.assertIn("`session-start.py` or `check-project-env.py`", text)

    def test_install_rule_keeps_deterministic_and_semantic_boundaries(self) -> None:
        text = self.read_rule()

        self.assertIn("fixed framework assets", text)
        self.assertIn("preserve existing `.harness/contracts/` and `work/`", text)
        self.assertIn("must not merge freeform entrypoint prose", text)
        self.assertIn("must not write `workflow-state.json`", text)
        self.assertIn("must not write `tasks.json`", text)
        self.assertIn("semantic conflict judgment belongs to `project-init`", text)
        self.assertIn("project environment facts belong in `.harness/contracts/project-contracts.json`", text)

    def test_install_rule_is_referenced_by_entrypoints_and_architecture(self) -> None:
        architecture = ARCHITECTURE.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")
        agents = AGENTS.read_text(encoding="utf-8")
        template = MANAGED_BLOCK_TEMPLATE.read_text(encoding="utf-8")

        for text in (architecture, readme, agents, template):
            self.assertIn(".harness/rules/install-rules.md", text)


if __name__ == "__main__":
    unittest.main()
