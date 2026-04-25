#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / ".harness" / "schemas" / "tasks.schema.json"
TEMPLATE = REPO_ROOT / ".harness" / "templates" / "tasks.template.json"


class TasksSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(self.schema)

    def assert_valid(self, data: dict) -> None:
        errors = sorted(
            Draft202012Validator(self.schema).iter_errors(data),
            key=lambda err: list(err.absolute_path),
        )
        self.assertEqual(errors, [])

    def assert_invalid(self, data: dict) -> None:
        errors = list(Draft202012Validator(self.schema).iter_errors(data))
        self.assertNotEqual(errors, [])

    def test_template_matches_schema(self) -> None:
        self.assert_valid(self.template)

    def test_reviewing_task_can_be_owned_by_reviewer(self) -> None:
        data = copy.deepcopy(self.template)
        task = data["tasks"][0]
        task["status"] = "reviewing"
        task["ownerRole"] = "reviewer"
        task["verification"]["lastResult"] = "passed"
        task["verification"]["checks"] = ["implementation matches acceptance"]

        self.assert_valid(data)

    def test_active_status_must_match_owner_role(self) -> None:
        data = copy.deepcopy(self.template)
        task = data["tasks"][0]
        task["status"] = "implementing"
        task["ownerRole"] = "tester"

        self.assert_invalid(data)


if __name__ == "__main__":
    unittest.main()
