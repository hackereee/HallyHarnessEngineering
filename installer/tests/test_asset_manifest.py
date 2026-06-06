#!/usr/bin/env python3

from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PACKAGE_ROOT = REPO_ROOT / "src" / "harness_engineering_installer"
MANIFEST = PACKAGE_ROOT / "assets-manifest.json"
PAYLOAD_ROOT = PACKAGE_ROOT / "payload"
PACKAGE_INIT = PACKAGE_ROOT / "__init__.py"
MIN_RELEASE_VERSION = (0, 1, 2)

EXCLUDED_SOURCE_PARTS = {"__pycache__"}
EXCLUDED_SOURCE_SUFFIXES = {".pyc", ".pyo"}
FORBIDDEN_FIXED_ASSETS = {
    "AGENTS.md",
    "README.md",
    "ARCHITECTURE.md",
}


def source_harness_assets() -> set[str]:
    assets: set[str] = set()
    for path in (REPO_ROOT / ".harness").rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if any(part in EXCLUDED_SOURCE_PARTS for part in path.parts):
            continue
        if path.suffix in EXCLUDED_SOURCE_SUFFIXES:
            continue
        assets.add(relative)
    return assets


def parse_version(raw: str) -> tuple[int, int, int]:
    parts = raw.split(".")
    if len(parts) != 3:
        raise AssertionError(f"version must use MAJOR.MINOR.PATCH: {raw}")
    return tuple(int(part) for part in parts)


def package_init_version() -> str:
    prefix = '__version__ = "'
    for line in PACKAGE_INIT.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix) and line.endswith('"'):
            return line[len(prefix) : -1]
    raise AssertionError("__version__ not found in package __init__.py")


class AssetManifestTest(unittest.TestCase):
    def read_manifest(self) -> dict:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_pyproject_declares_cli_package(self) -> None:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["name"], "hally-harness-engineering")
        self.assertEqual(data["project"]["requires-python"], ">=3.11")
        self.assertEqual(
            data["project"]["scripts"]["hally-harness-engineering"],
            "harness_engineering_installer.cli:main",
        )
        self.assertIn("jsonschema>=4.18", data["project"]["dependencies"])
        self.assertIn(
            "payload/.harness/**/*",
            data["tool"]["setuptools"]["package-data"]["harness_engineering_installer"],
        )

    def test_package_version_is_upgraded_and_synchronized(self) -> None:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        version = data["project"]["version"]

        self.assertGreaterEqual(parse_version(version), MIN_RELEASE_VERSION)
        self.assertEqual(package_init_version(), version)

    def test_manifest_lists_assets_and_boundaries(self) -> None:
        manifest = self.read_manifest()

        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertIn(".harness/ARCHITECTURE.md", manifest["fixedAssets"])
        self.assertIn(".harness/rules/task-level.md", manifest["fixedAssets"])
        self.assertIn(".harness/rules/llm-script-boundary.md", manifest["fixedAssets"])
        self.assertIn(".harness/rules/workflow-gates.md", manifest["fixedAssets"])
        self.assertIn(".harness/contracts/.gitkeep", manifest["fixedAssets"])
        self.assertIn(".harness/skills/project-update/SKILL.md", manifest["fixedAssets"])
        self.assertIn(".harness/contracts/", manifest["preservePaths"])
        self.assertIn("work/", manifest["preservePaths"])
        self.assertEqual(
            set(manifest["forbiddenRootFiles"]),
            FORBIDDEN_FIXED_ASSETS,
        )
        self.assertIn(".harness/rules/install-rules.md", manifest["retiredAssets"])

    def test_manifest_excludes_runtime_and_root_files(self) -> None:
        manifest = self.read_manifest()
        fixed_assets = set(manifest["fixedAssets"])

        self.assertTrue(all(asset.startswith(".harness/") for asset in fixed_assets))
        self.assertFalse(any(asset.startswith("work/") for asset in fixed_assets))
        self.assertTrue(FORBIDDEN_FIXED_ASSETS.isdisjoint(fixed_assets))
        self.assertFalse(any("__pycache__" in asset for asset in fixed_assets))
        self.assertFalse(any(asset.endswith((".pyc", ".pyo")) for asset in fixed_assets))

    def test_payload_contains_every_manifest_asset(self) -> None:
        manifest = self.read_manifest()

        missing = [
            asset
            for asset in manifest["fixedAssets"]
            if not (PAYLOAD_ROOT / asset).is_file()
        ]
        self.assertEqual(missing, [])

    def test_payload_matches_source_harness_assets(self) -> None:
        manifest = self.read_manifest()

        mismatched = [
            asset
            for asset in manifest["fixedAssets"]
            if asset.startswith(".harness/")
            and (REPO_ROOT / asset).read_bytes() != (PAYLOAD_ROOT / asset).read_bytes()
        ]
        self.assertEqual(mismatched, [])

    def test_every_source_harness_asset_is_manifested(self) -> None:
        manifest = self.read_manifest()
        fixed_assets = set(manifest["fixedAssets"])

        self.assertEqual(source_harness_assets() - fixed_assets, set())


if __name__ == "__main__":
    unittest.main()
