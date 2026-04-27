#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from jsonschema.validators import extend


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / ".harness" / "schemas" / "backlogs.schema.json"
TEMPLATE = REPO_ROOT / ".harness" / "templates" / "backlogs.template.json"


def unique_item_properties(validator, properties, instance, schema):
    if not isinstance(instance, list):
        return
    for property_name in properties:
        seen: dict[object, int] = {}
        for index, item in enumerate(instance):
            if not isinstance(item, dict) or property_name not in item:
                continue
            value = item[property_name]
            if value in seen:
                yield ValidationError(
                    f"{property_name!r} must be unique; {value!r} appears at indexes "
                    f"{seen[value]} and {index}"
                )
            seen[value] = index


BacklogsValidator = extend(
    Draft202012Validator,
    validators={"x-harness-uniqueItemProperties": unique_item_properties},
)


def valid_item(**overrides: object) -> dict:
    item = {
        "id": "BL-001",
        "title": "Add backlog intake",
        "summary": "Record new incoming work without mutating the active workflow.",
        "dispatch": "queue",
        "sourceRef": "chat:2026-04-27-001",
        "createdAt": "2026-04-27T09:00:00+08:00",
        "notes": "Initial intake contract.",
    }
    item.update(overrides)
    return item


class BacklogsSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(self.schema)
        self.validator = BacklogsValidator(self.schema)

    def assert_valid(self, data: dict) -> None:
        errors = sorted(self.validator.iter_errors(data), key=lambda err: list(err.absolute_path))
        self.assertEqual(errors, [])

    def assert_invalid(self, data: dict) -> None:
        errors = list(self.validator.iter_errors(data))
        self.assertNotEqual(errors, [])

    def test_template_matches_schema(self) -> None:
        self.assert_valid(self.template)
        self.assertEqual(self.template["$schema"], "../schemas/backlogs.schema.json")
        self.assertEqual(self.template["items"], [])

    def test_valid_backlog_item_shape(self) -> None:
        self.assert_valid(
            {
                "$schema": "../schemas/backlogs.schema.json",
                "items": [valid_item()],
            }
        )

    def test_backlog_item_ids_use_bl_sequence_and_are_unique(self) -> None:
        invalid_id = {
            "$schema": "../schemas/backlogs.schema.json",
            "items": [valid_item(id="TASK-001")],
        }
        duplicate_id = {
            "$schema": "../schemas/backlogs.schema.json",
            "items": [
                valid_item(id="BL-001"),
                valid_item(id="BL-001", sourceRef="chat:2026-04-27-002"),
            ],
        }

        self.assert_invalid(invalid_id)
        self.assert_invalid(duplicate_id)

    def test_dispatch_is_limited_to_queue_or_preempt(self) -> None:
        valid_preempt = {
            "$schema": "../schemas/backlogs.schema.json",
            "items": [valid_item(dispatch="preempt")],
        }
        invalid_dispatch = copy.deepcopy(valid_preempt)
        invalid_dispatch["items"][0]["dispatch"] = "now"

        self.assert_valid(valid_preempt)
        self.assert_invalid(invalid_dispatch)

    def test_source_ref_and_created_at_are_required_audit_fields(self) -> None:
        missing_source = valid_item()
        missing_source.pop("sourceRef")
        missing_created = valid_item()
        missing_created.pop("createdAt")
        legacy_snake_case = valid_item()
        legacy_snake_case["source_ref"] = legacy_snake_case.pop("sourceRef")
        legacy_snake_case["created_at"] = legacy_snake_case.pop("createdAt")

        for item in (missing_source, missing_created, legacy_snake_case):
            with self.subTest(item=item):
                self.assert_invalid(
                    {
                        "$schema": "../schemas/backlogs.schema.json",
                        "items": [item],
                    }
                )


if __name__ == "__main__":
    unittest.main()
