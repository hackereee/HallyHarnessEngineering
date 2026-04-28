#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from harness_engineering_installer import __version__  # noqa: E402
from harness_engineering_installer.cli import main  # noqa: E402


class InstallerCliTest(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_version_prints_package_version(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue(), f"hally-harness-engineering {__version__}\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_install_dry_run_prints_operations_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"

            code, stdout, stderr = self.run_cli(["install", str(target), "--dry-run"])

            self.assertEqual(code, 0, stderr)
            self.assertIn("copy .harness/ARCHITECTURE.md", stdout)
            self.assertFalse((target / ".harness").exists())

    def test_install_writes_bundled_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"

            code, stdout, stderr = self.run_cli(["install", str(target)])

            self.assertEqual(code, 0, stderr)
            self.assertIn("copied", stdout)
            self.assertTrue((target / ".harness" / "ARCHITECTURE.md").is_file())

    def test_update_prunes_retired_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            retired = target / ".harness" / "rules" / "install-rules.md"
            retired.parent.mkdir(parents=True)
            retired.write_text("old install rule\n", encoding="utf-8")

            code, stdout, stderr = self.run_cli(["update", str(target)])

            self.assertEqual(code, 0, stderr)
            self.assertIn("pruned", stdout)
            self.assertFalse(retired.exists())

    def test_check_returns_nonzero_when_assets_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()

            code, stdout, stderr = self.run_cli(["check", str(target)])

            self.assertEqual(code, 1)
            self.assertIn("missing .harness/ARCHITECTURE.md", stdout)
            self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()
