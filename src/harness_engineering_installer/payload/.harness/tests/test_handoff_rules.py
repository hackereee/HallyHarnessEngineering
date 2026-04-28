#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RULE = REPO_ROOT / ".harness" / "rules" / "handoff-rules.md"
TEMPLATE = REPO_ROOT / ".harness" / "templates" / "handoff.template.md"
DESIGN_NOTE = REPO_ROOT / "harness-design" / "handoff.template.md"


REQUIRED_HEADER_FIELDS = (
    "workflowId",
    "planRef",
    "activeTaskId",
    "currentPhase",
    "taskStatus",
    "ownerRole",
    "sourceSessionId",
)

REQUIRED_SECTIONS = (
    "## Current Status",
    "## Role Handoff",
    "## Risks",
    "## Next Action",
)


class HandoffRulesTest(unittest.TestCase):
    def test_handoff_rules_define_truth_sources_and_lifecycle_entry_shape(self) -> None:
        text = RULE.read_text(encoding="utf-8")

        self.assertIn("workflow-state.json", text)
        self.assertIn("tasks.json", text)
        self.assertIn("handoff.md", text)
        self.assertIn("recovery summary", text)
        self.assertIn("not a truth source", text)
        for field in REQUIRED_HEADER_FIELDS:
            self.assertIn(field, text)
        for section in REQUIRED_SECTIONS:
            self.assertIn(section, text)
        self.assertIn("## Lifecycle Transaction -", text)
        self.assertIn("stateSource", text)

    def test_handoff_template_contains_required_header_fields_and_sections(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertTrue(text.startswith("# Handoff\n"))
        for field in REQUIRED_HEADER_FIELDS:
            self.assertIn(f"- {field}:", text)
        for section in REQUIRED_SECTIONS:
            self.assertIn(section, text)
        self.assertIn("stateSource: workflow-state.json and tasks.json", text)

    def test_design_note_points_to_canonical_rule_and_template(self) -> None:
        text = DESIGN_NOTE.read_text(encoding="utf-8")

        self.assertIn(".harness/templates/handoff.template.md", text)
        self.assertIn(".harness/rules/handoff-rules.md", text)
        self.assertIn("work/workflow-state.json", text)
        self.assertIn("work/plans/active/<PLAN-ID>/tasks.json", text)


if __name__ == "__main__":
    unittest.main()
