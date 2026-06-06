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

    def test_requires_workflow_integration_review_across_all_entrypoints(self) -> None:
        text = self.read_skill()

        self.assertIn("## Workflow Integration Review", text)
        self.assertIn("read all detected entrypoints", text)
        self.assertIn("before workflow conclusions", text)
        self.assertIn("CLAUDE.md", text)
        self.assertIn("GEMINI.md", text)
        self.assertIn(".github/copilot-instructions.md", text)

    def test_maps_target_workflow_rules_to_harness_gates(self) -> None:
        text = self.read_skill()

        self.assertIn("planning maps to `planning`", text)
        self.assertIn("new workflow start maps to `start-workflow.py`", text)
        self.assertIn("development maps to `implementing`", text)
        self.assertIn("tests map to the `testing` gate", text)
        self.assertIn("reviews map to the `reviewing` gate", text)
        self.assertIn("commit-task.py", text)
        self.assertIn("archive-plan.py", text)
        self.assertIn("backlog-intake.py", text)
        self.assertIn("backlog-consume.py", text)

    def test_conflicts_are_reported_before_user_prose_changes(self) -> None:
        text = self.read_skill()

        self.assertIn("report conflicts before modifying user-owned prose", text)
        self.assertIn("semantic conflict judgment belongs to the LLM, not `init-project-entrypoint.py`", text)
        self.assertIn("Do not parse freeform entrypoint prose in deterministic scripts", text)
        self.assertIn("state-write.py", text)
        self.assertIn("update-task.py", text)
        self.assertIn("Entry point managed block updates must not re-run or overwrite", text)

    def test_requires_harness_assets_to_be_installed_before_project_init(self) -> None:
        text = self.read_skill()

        self.assertIn("## Installed Harness Assets Precondition", text)
        self.assertIn("fixed `.harness/` assets", text)
        self.assertIn("deterministic installer", text)
        self.assertIn("HARNESS_ASSETS_MISSING", text)
        self.assertNotIn("install or verify `.harness/ARCHITECTURE.md`", text)

    def test_project_init_defers_existing_project_updates_to_project_update(self) -> None:
        text = self.read_skill()

        self.assertIn("project-update", text)
        self.assertIn("already-onboarded", text)
        self.assertIn("after installer update", text)
        self.assertIn("first onboarding", text)

    def test_project_init_forbids_creating_source_design_notes_in_target_project(self) -> None:
        text = self.read_skill()

        self.assertIn("Do not create `harness-design/`", text)
        self.assertIn(".harness/rules/task-level.md", text)

    def test_project_init_forbids_creating_installer_lifecycle_docs_in_target_project(self) -> None:
        text = self.read_skill()

        self.assertIn("Do not create `installer/install-lifecycle.md`", text)
        self.assertIn("source distribution repository only", text)

    def test_entrypoint_integration_is_not_full_text_merge(self) -> None:
        text = self.read_skill()

        self.assertIn("not a full-text merge", text)
        self.assertIn("only the canonical entrypoint receives the Harness managed block by default", text)
        self.assertIn("tool-specific entrypoints are read for semantic review", text)
        self.assertIn("not auto-merged", text)
        self.assertIn("marker outside", text)

    def test_architecture_documents_project_init_skill_boundary(self) -> None:
        text = HARNESS_ARCHITECTURE.read_text(encoding="utf-8")

        self.assertIn(".harness/skills/project-init/SKILL.md", text)
        self.assertIn(".harness/skills/project-env-contract/SKILL.md", text)
        self.assertIn(".harness/ARCHITECTURE.md", text)
        self.assertIn("root `ARCHITECTURE.md`", text)
        self.assertIn("business architecture", text)

    def test_architecture_documents_entrypoint_integration_boundary(self) -> None:
        text = HARNESS_ARCHITECTURE.read_text(encoding="utf-8")
        lowered = text.lower()

        self.assertIn("target agent entrypoint integration", text)
        self.assertIn("workflow mapping layer", text)
        self.assertIn("root `architecture.md` remains target project business architecture", lowered)
        self.assertIn("`.harness/architecture.md` remains harness framework architecture", lowered)
        self.assertIn(
            "`project-entrypoints.json` is deterministic entrypoint metadata, not a semantic conflict report",
            text,
        )
        self.assertNotIn("harness-design/architecture.md", text)

    def test_harness_architecture_doc_exists(self) -> None:
        text = HARNESS_ARCHITECTURE.read_text(encoding="utf-8")

        self.assertIn("# Harness Framework Architecture", text)
        self.assertIn(".harness/", text)
        self.assertIn("work/", text)

    def test_legacy_harness_design_architecture_is_removed(self) -> None:
        self.assertFalse(LEGACY_ARCHITECTURE.exists())


if __name__ == "__main__":
    unittest.main()
