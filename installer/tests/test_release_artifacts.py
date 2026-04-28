#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
import tarfile
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
README = REPO_ROOT / "README.md"
CHECK_ARTIFACTS = REPO_ROOT / "installer" / "release" / "check_artifacts.py"


def load_check_artifacts_module():
    spec = importlib.util.spec_from_file_location("check_artifacts", CHECK_ARTIFACTS)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {CHECK_ARTIFACTS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["version"]


def artifact_stem(version: str) -> str:
    return f"hally_harness_engineering-{version}"


def write_sdist(dist: Path, version: str) -> Path:
    path = dist / f"{artifact_stem(version)}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(f"{artifact_stem(version)}/PKG-INFO")
        payload = f"Name: hally-harness-engineering\nVersion: {version}\n".encode()
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return path


def write_wheel(
    dist: Path,
    version: str,
    *,
    metadata_name: str = "hally-harness-engineering",
    include_dependency: bool = True,
    include_entry_point: bool = True,
    payload_assets: tuple[str, ...] | None = None,
) -> Path:
    path = dist / f"{artifact_stem(version)}-py3-none-any.whl"
    dist_info = f"hally_harness_engineering-{version}.dist-info"
    metadata_lines = [
        "Metadata-Version: 2.1",
        f"Name: {metadata_name}",
        f"Version: {version}",
    ]
    if include_dependency:
        metadata_lines.append("Requires-Dist: jsonschema>=4.18")

    if payload_assets is None:
        payload_assets = (
            "harness_engineering_installer/payload/.harness/ARCHITECTURE.md",
            "harness_engineering_installer/payload/.harness/schemas/workflow-state.schema.json",
            "harness_engineering_installer/payload/.harness/scripts/harness",
            "harness_engineering_installer/payload/.harness/templates/plan.template.md",
            "harness_engineering_installer/payload/.harness/skills/project-init/SKILL.md",
            "harness_engineering_installer/payload/.harness/rules/workflow-lifecycle.md",
        )

    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr(f"{dist_info}/METADATA", "\n".join(metadata_lines) + "\n")
        if include_entry_point:
            wheel.writestr(
                f"{dist_info}/entry_points.txt",
                "[console_scripts]\n"
                "hally-harness-engineering = harness_engineering_installer.cli:main\n",
            )
        for asset in payload_assets:
            wheel.writestr(asset, "payload\n")
    return path


class ReleaseArtifactsTest(unittest.TestCase):
    def run_main(self, dist: Path) -> tuple[int, str, str]:
        module = load_check_artifacts_module()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = module.main([str(dist)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_valid_dist_reports_required_release_checks(self) -> None:
        version = project_version()
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_sdist(dist, version)
            write_wheel(dist, version)

            code, stdout, stderr = self.run_main(dist)

            self.assertEqual(code, 0, stderr)
            self.assertIn("package: hally-harness-engineering", stdout)
            self.assertIn(f"version: {version}", stdout)
            self.assertIn(f"wheel: {artifact_stem(version)}-py3-none-any.whl", stdout)
            self.assertIn(f"sdist: {artifact_stem(version)}.tar.gz", stdout)
            self.assertIn("entry point: hally-harness-engineering = harness_engineering_installer.cli:main", stdout)
            self.assertIn("dependency: jsonschema>=4.18", stdout)
            self.assertIn("payload: architecture, schemas, scripts, templates, skills, rules", stdout)

    def test_missing_wheel_fails_with_specific_message(self) -> None:
        version = project_version()
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_sdist(dist, version)

            code, _stdout, stderr = self.run_main(dist)

            self.assertNotEqual(code, 0)
            self.assertIn(f"missing wheel {artifact_stem(version)}-py3-none-any.whl", stderr)

    def test_extra_distribution_artifact_fails_with_specific_message(self) -> None:
        version = project_version()
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_sdist(dist, version)
            write_wheel(dist, version)
            (dist / "hally_harness_engineering-0.0.1-py3-none-any.whl").write_text("old wheel\n", encoding="utf-8")

            code, _stdout, stderr = self.run_main(dist)

            self.assertNotEqual(code, 0)
            self.assertIn("unexpected distribution artifact", stderr)

    def test_missing_console_script_fails_with_specific_message(self) -> None:
        version = project_version()
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_sdist(dist, version)
            write_wheel(dist, version, include_entry_point=False)

            code, _stdout, stderr = self.run_main(dist)

            self.assertNotEqual(code, 0)
            self.assertIn("missing console script hally-harness-engineering = harness_engineering_installer.cli:main", stderr)

    def test_missing_dependency_fails_with_specific_message(self) -> None:
        version = project_version()
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_sdist(dist, version)
            write_wheel(dist, version, include_dependency=False)

            code, _stdout, stderr = self.run_main(dist)

            self.assertNotEqual(code, 0)
            self.assertIn("missing dependency jsonschema>=4.18", stderr)

    def test_missing_payload_category_fails_with_specific_message(self) -> None:
        version = project_version()
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_sdist(dist, version)
            write_wheel(
                dist,
                version,
                payload_assets=(
                    "harness_engineering_installer/payload/.harness/ARCHITECTURE.md",
                    "harness_engineering_installer/payload/.harness/schemas/workflow-state.schema.json",
                    "harness_engineering_installer/payload/.harness/templates/plan.template.md",
                    "harness_engineering_installer/payload/.harness/skills/project-init/SKILL.md",
                    "harness_engineering_installer/payload/.harness/rules/workflow-lifecycle.md",
                ),
            )

            code, _stdout, stderr = self.run_main(dist)

            self.assertNotEqual(code, 0)
            self.assertIn("missing payload asset under harness_engineering_installer/payload/.harness/scripts/", stderr)

    def test_readme_records_local_artifact_inspection_gate(self) -> None:
        text = README.read_text(encoding="utf-8")

        self.assertIn("python3 -m build", text)
        self.assertIn("python3 installer/release/check_artifacts.py dist", text)
        self.assertIn("pre-publish release gate", text)


if __name__ == "__main__":
    unittest.main()
