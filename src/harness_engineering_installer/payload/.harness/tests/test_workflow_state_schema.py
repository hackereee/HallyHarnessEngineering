#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / ".harness" / "schemas" / "workflow-state.schema.json"
TEMPLATE = REPO_ROOT / ".harness" / "templates" / "workflow-state.template.json"


class WorkflowStateSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(self.schema)
        self.validator = Draft202012Validator(self.schema)

    def assert_valid(self, data: dict) -> None:
        errors = sorted(self.validator.iter_errors(data), key=lambda err: list(err.absolute_path))
        self.assertEqual(errors, [])

    def assert_invalid(self, data: dict) -> None:
        errors = list(self.validator.iter_errors(data))
        self.assertNotEqual(errors, [])

    def test_template_matches_schema(self) -> None:
        self.assert_valid(self.template)

    def test_schema_field_is_required(self) -> None:
        data = copy.deepcopy(self.template)
        data.pop("$schema")

        self.assert_invalid(data)

    def test_direct_workflow_cannot_have_active_task_without_plan(self) -> None:
        data = copy.deepcopy(self.template)
        data["activePlanRef"] = None
        data["activeTaskId"] = "TASK-001"
        data["currentPhase"] = "implementing"
        data["ownerRole"] = "developer"

        self.assert_invalid(data)

    def test_archived_workflow_cannot_retain_active_plan_ref(self) -> None:
        data = copy.deepcopy(self.template)
        data["workflowStatus"] = "archived"
        data["currentPhase"] = "archiving"
        data["ownerRole"] = "developer"
        data["activePlanRef"] = "./plans/active/PLAN-001/plan.md"
        data["activeTaskId"] = None
        data["nextAction"] = "开启下一个 workflow"

        self.assert_invalid(data)

    def test_completed_workflow_keeps_final_review_gate_shape(self) -> None:
        data = copy.deepcopy(self.template)
        data["workflowStatus"] = "completed"
        data["currentPhase"] = "reviewing"
        data["ownerRole"] = "reviewer"
        data["activePlanRef"] = None
        data["activeTaskId"] = None
        data["nextAction"] = "开启下一个 workflow"
        self.assert_valid(data)

        invalid_phase = copy.deepcopy(data)
        invalid_phase["currentPhase"] = "archiving"
        invalid_phase["ownerRole"] = "developer"
        self.assert_invalid(invalid_phase)

    def test_paused_status_is_not_a_supported_runtime_shape(self) -> None:
        data = copy.deepcopy(self.template)
        data["workflowStatus"] = "paused"

        self.assert_invalid(data)

    def test_active_planning_requires_active_plan_ref(self) -> None:
        data = copy.deepcopy(self.template)
        data["workflowStatus"] = "active"
        data["currentPhase"] = "planning"
        data["ownerRole"] = "planner"
        data["activePlanRef"] = None
        data["activeTaskId"] = None
        data["nextAction"] = "Materialize active plan package"

        self.assert_invalid(data)

    def test_active_archiving_requires_active_plan_ref(self) -> None:
        data = copy.deepcopy(self.template)
        data["workflowStatus"] = "active"
        data["currentPhase"] = "archiving"
        data["ownerRole"] = "developer"
        data["activePlanRef"] = None
        data["activeTaskId"] = None
        data["nextAction"] = "Archive active plan package"

        self.assert_invalid(data)


if __name__ == "__main__":
    unittest.main()
