#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / ".harness" / "schemas" / "project-entrypoints.schema.json"
TEMPLATE = REPO_ROOT / ".harness" / "templates" / "project-entrypoints.template.json"


class ProjectEntrypointsSchemaTest(unittest.TestCase):
    def load_schema(self) -> dict:
        return json.loads(SCHEMA.read_text(encoding="utf-8"))

    def load_template(self) -> dict:
        return json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def validate(self, data: dict) -> list[str]:
        schema = self.load_schema()
        return [
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path))
        ]

    def test_template_validates_against_schema(self) -> None:
        errors = self.validate(self.load_template())

        self.assertEqual(errors, [])

    def test_template_names_canonical_entry_and_harness_architecture(self) -> None:
        template = self.load_template()

        self.assertEqual(template["contractVersion"], "project-entrypoints-v1")
        self.assertEqual(template["canonicalEntry"], "AGENTS.md")
        self.assertEqual(template["harnessArchitectureRef"], ".harness/ARCHITECTURE.md")
        self.assertGreaterEqual(len(template["detectedEntries"]), 1)

    def test_detected_entries_require_kind_block_status_and_evidence(self) -> None:
        template = self.load_template()
        entry = template["detectedEntries"][0]

        self.assertIn(entry["kind"], ("generic-agent", "tool-agent", "editor-rule"))
        self.assertIn(entry["harnessBlock"], ("present", "absent", "not-applicable"))
        self.assertIn("path", entry)
        self.assertIn("evidenceSource", entry)

    def test_invalid_entry_kind_is_rejected(self) -> None:
        data = self.load_template()
        data["detectedEntries"][0]["kind"] = "readme"

        errors = self.validate(data)

        self.assertTrue(any("detectedEntries/0/kind" in error for error in errors), errors)

    def test_harness_architecture_ref_is_stable(self) -> None:
        data = self.load_template()
        data["harnessArchitectureRef"] = "harness-design/architecture.md"

        errors = self.validate(data)

        self.assertTrue(any("harnessArchitectureRef" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
