#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-python-package.yml"
RELEASE_DOC = REPO_ROOT / "docs" / "release" / "package-registry-release.md"
README = REPO_ROOT / "README.md"
INSTALL_LIFECYCLE = REPO_ROOT / "installer" / "install-lifecycle.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class ReleaseDocsTest(unittest.TestCase):
    def test_workflow_is_manual_and_requires_registry_choice(self) -> None:
        text = read(WORKFLOW)

        self.assertIn("workflow_dispatch:", text)
        self.assertIn("registry:", text)
        self.assertIn("type: choice", text)
        self.assertIn("testpypi", text)
        self.assertIn("pypi", text)

    def test_workflow_runs_local_gates_before_publish_steps(self) -> None:
        text = read(WORKFLOW)

        gates = [
            "python3 -m unittest discover -s installer/tests -p 'test_*.py'",
            "python3 -m build",
            "python3 installer/release/check_artifacts.py dist",
            "python3 installer/release/smoke_install.py dist",
        ]
        positions = [text.index(gate) for gate in gates]
        first_publish = text.index("pypa/gh-action-pypi-publish@release/v1")

        self.assertEqual(positions, sorted(positions))
        self.assertLess(max(positions), first_publish)

    def test_workflow_uses_trusted_publishing_without_password_secrets(self) -> None:
        text = read(WORKFLOW)

        self.assertIn("id-token: write", text)
        self.assertIn("pypa/gh-action-pypi-publish@release/v1", text)
        self.assertIn("repository-url: https://test.pypi.org/legacy/", text)
        self.assertIn("environment: pypi", text)
        self.assertIn("if: ${{ inputs.registry == 'pypi' }}", text)
        self.assertNotIn("PYPI_TOKEN", text)
        self.assertNotIn("password:", text)

    def test_release_document_covers_registry_operation_and_recovery(self) -> None:
        text = read(RELEASE_DOC)

        required = [
            "Trusted Publisher",
            "TestPyPI",
            "PyPI",
            "version bump",
            "pipx install hally-harness-engineering",
            "pipx upgrade hally-harness-engineering",
            "uv tool install hally-harness-engineering",
            "uv tool upgrade hally-harness-engineering",
            "yank",
            "external release operation",
            "not a Harness runtime workflow gate",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_readme_and_installer_lifecycle_link_release_docs(self) -> None:
        readme = read(README)
        lifecycle = read(INSTALL_LIFECYCLE)

        self.assertIn("docs/release/package-registry-release.md", readme)
        self.assertIn("publish-python-package.yml", readme)
        self.assertIn("docs/release/package-registry-release.md", lifecycle)
        self.assertIn("publish-python-package.yml", lifecycle)


if __name__ == "__main__":
    unittest.main()
