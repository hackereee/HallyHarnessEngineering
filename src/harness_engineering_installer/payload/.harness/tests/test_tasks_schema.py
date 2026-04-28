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

    def done_task_manifest(self, review: dict | None = None) -> dict:
        data = copy.deepcopy(self.template)
        task = data["tasks"][0]
        task["status"] = "done"
        task["ownerRole"] = "developer"
        task["acceptance"] = ["Review gate acceptance is met"]
        task["verification"]["lastResult"] = "passed"
        task["verification"]["checks"] = ["Verification evidence exists"]
        if review is None:
            task.pop("review", None)
        else:
            task["review"] = review
        return data

    def passing_review(self) -> dict:
        return {
            "score": 90,
            "threshold": 85,
            "lastResult": "passed",
            "rubricVersion": "review-rubric-v1",
            "checks": ["schema sync checked"],
            "findings": [],
            "reportRef": "work/sessions/2026-04-27/session-review.md",
        }

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

    def test_done_task_requires_passing_review_gate(self) -> None:
        self.assert_valid(self.done_task_manifest(self.passing_review()))

        critical_finding = {
            "severity": "critical",
            "blocking": True,
            "summary": "Task bypasses a Harness invariant",
        }
        blocking_important_finding = {
            "severity": "important",
            "blocking": True,
            "summary": "Task leaves required lifecycle tests uncovered",
        }
        blocking_minor_finding = {
            "severity": "minor",
            "blocking": True,
            "summary": "Wording can be clearer",
        }
        nonblocking_minor_finding = {
            "severity": "minor",
            "blocking": False,
            "summary": "Wording can be clearer",
        }

        invalid_cases = [
            ("missing review", self.done_task_manifest()),
            (
                "review not passed",
                self.done_task_manifest({**self.passing_review(), "lastResult": "failed"}),
            ),
            (
                "score below threshold",
                self.done_task_manifest({**self.passing_review(), "score": 84}),
            ),
            (
                "critical finding",
                self.done_task_manifest({**self.passing_review(), "findings": [critical_finding]}),
            ),
            (
                "blocking important finding",
                self.done_task_manifest({**self.passing_review(), "findings": [blocking_important_finding]}),
            ),
            (
                "blocking minor finding",
                self.done_task_manifest({**self.passing_review(), "findings": [blocking_minor_finding]}),
            ),
        ]

        for label, data in invalid_cases:
            with self.subTest(label=label):
                self.assert_invalid(data)

        self.assert_valid(
            self.done_task_manifest({**self.passing_review(), "findings": [nonblocking_minor_finding]})
        )


if __name__ == "__main__":
    unittest.main()
