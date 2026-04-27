#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / ".harness" / "schemas" / "project-contracts.schema.json"
TEMPLATE = REPO_ROOT / ".harness" / "templates" / "project-contracts.template.json"


class ProjectContractsSchemaTest(unittest.TestCase):
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

    def test_template_contains_contract_truth_source_sections(self) -> None:
        template = self.load_template()

        self.assertIn("projectProfile", template)
        self.assertIn("commandRegistry", template)
        self.assertIn("environmentChecks", template)
        self.assertIn("adapterFallbacks", template)
        self.assertEqual(template["contractVersion"], "project-contracts-v1")

    def test_environment_checks_require_evidence_severity_and_execution_source(self) -> None:
        template = self.load_template()
        checks = template["environmentChecks"]

        self.assertGreaterEqual(len(checks), 2)
        for check in checks:
            self.assertIn("id", check)
            self.assertIn("description", check)
            self.assertIn("evidenceSource", check)
            self.assertIn(check["severity"], ("blocking", "warning"))
            self.assertTrue(("commandRef" in check) ^ ("probe" in check))

    def test_invalid_severity_is_rejected(self) -> None:
        data = self.load_template()
        data["environmentChecks"][0]["severity"] = "optional"

        errors = self.validate(data)

        self.assertTrue(any("environmentChecks/0/severity" in error for error in errors), errors)

    def test_check_without_command_or_probe_is_rejected(self) -> None:
        data = self.load_template()
        data["environmentChecks"][0].pop("probe", None)
        data["environmentChecks"][0].pop("commandRef", None)

        errors = self.validate(data)

        self.assertTrue(any("environmentChecks/0" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
