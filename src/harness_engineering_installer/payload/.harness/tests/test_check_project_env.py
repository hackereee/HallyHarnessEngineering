#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".harness" / "scripts" / "check-project-env.py"
SCHEMA = REPO_ROOT / ".harness" / "schemas" / "project-contracts.schema.json"
TEMPLATE = REPO_ROOT / ".harness" / "templates" / "project-contracts.template.json"


class CheckProjectEnvTest(unittest.TestCase):
    def base_contract(self) -> dict:
        return json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def write_contract(self, root: Path, contract: dict) -> Path:
        path = root / "project-contracts.json"
        path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def run_checker(self, root: Path, contract: Path | None = None) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(root),
            "--schema",
            str(SCHEMA),
        ]
        if contract is not None:
            command.extend(["--contract", str(contract)])
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_default_missing_contract_returns_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
            self.assertIn("NOT_CONFIGURED project environment contract missing", result.stdout)
            self.assertIn(".harness/contracts/project-contracts.json", result.stdout)
            self.assertEqual(result.stderr, "")

    def test_explicit_missing_contract_returns_not_configured_with_requested_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_contract = root / "custom" / "missing-contract.json"

            result = self.run_checker(root, missing_contract)

            self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
            self.assertIn("NOT_CONFIGURED project environment contract missing", result.stdout)
            self.assertIn(str(missing_contract), result.stdout)
            self.assertEqual(result.stderr, "")

    def test_blocking_probe_failure_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self.base_contract()
            contract["environmentChecks"] = [
                {
                    "id": "required-file",
                    "description": "A required file exists.",
                    "severity": "blocking",
                    "evidenceSource": "fixture",
                    "probe": {"type": "path_exists", "path": "missing.txt"},
                    "expectedResult": "missing.txt exists",
                    "remediation": "Create missing.txt.",
                }
            ]

            result = self.run_checker(root, self.write_contract(root, contract))

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("FAIL blocking required-file", result.stdout)
            self.assertIn("evidence=fixture", result.stdout)

    def test_warning_probe_failure_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self.base_contract()
            contract["environmentChecks"] = [
                {
                    "id": "optional-file",
                    "description": "An optional file exists.",
                    "severity": "warning",
                    "evidenceSource": "fixture",
                    "probe": {"type": "path_exists", "path": "missing.txt"},
                    "expectedResult": "missing.txt exists",
                    "remediation": "Create missing.txt if this warning matters.",
                }
            ]

            result = self.run_checker(root, self.write_contract(root, contract))

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("FAIL warning optional-file", result.stdout)

    def test_command_ref_executes_registered_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self.base_contract()
            contract["commandRegistry"] = [
                {
                    "id": "print-ok",
                    "description": "Print OK.",
                    "command": [sys.executable, "-c", "print('ok')"],
                    "cwd": ".",
                    "timeoutSeconds": 30,
                    "evidenceSource": "fixture",
                }
            ]
            contract["environmentChecks"] = [
                {
                    "id": "command-check",
                    "description": "Registered command exits successfully.",
                    "severity": "blocking",
                    "evidenceSource": "fixture",
                    "commandRef": "print-ok",
                    "expectedResult": "command exits with code 0",
                    "remediation": "Fix the command.",
                }
            ]

            result = self.run_checker(root, self.write_contract(root, contract))

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("PASS blocking command-check", result.stdout)

    def test_invalid_contract_is_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self.base_contract()
            contract.pop("projectProfile")

            result = self.run_checker(root, self.write_contract(root, contract))

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("schema validation failed", result.stderr)

    def test_duplicate_command_ids_are_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self.base_contract()
            contract["commandRegistry"] = [
                {
                    "id": "duplicate-command",
                    "description": "First command.",
                    "command": [sys.executable, "-c", "print('first')"],
                    "evidenceSource": "fixture",
                },
                {
                    "id": "duplicate-command",
                    "description": "Second command.",
                    "command": [sys.executable, "-c", "print('second')"],
                    "evidenceSource": "fixture",
                },
            ]

            result = self.run_checker(root, self.write_contract(root, contract))

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("duplicate commandRegistry id", result.stderr)

    def test_unknown_command_ref_is_contract_error_even_for_warning_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self.base_contract()
            contract["commandRegistry"] = []
            contract["environmentChecks"] = [
                {
                    "id": "unknown-ref",
                    "description": "Unknown command reference.",
                    "severity": "warning",
                    "evidenceSource": "fixture",
                    "commandRef": "missing-command",
                    "expectedResult": "command exists",
                    "remediation": "Fix commandRef.",
                }
            ]

            result = self.run_checker(root, self.write_contract(root, contract))

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("unknown commandRef", result.stderr)

    def test_duplicate_environment_check_ids_are_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self.base_contract()
            duplicate_check = {
                "id": "duplicate-check",
                "description": "A duplicate check.",
                "severity": "warning",
                "evidenceSource": "fixture",
                "probe": {"type": "path_exists", "path": "missing.txt"},
                "expectedResult": "missing.txt exists",
                "remediation": "Create missing.txt.",
            }
            contract["environmentChecks"] = [duplicate_check, dict(duplicate_check)]

            result = self.run_checker(root, self.write_contract(root, contract))

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("duplicate environmentChecks id", result.stderr)


if __name__ == "__main__":
    unittest.main()
