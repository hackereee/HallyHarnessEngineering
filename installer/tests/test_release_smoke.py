#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
SMOKE_INSTALL = REPO_ROOT / "installer" / "release" / "smoke_install.py"
INSTALL_DOC = REPO_ROOT / "installer" / "install-lifecycle.md"


class FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    def __init__(
        self,
        *,
        dry_run_writes: bool = False,
        check_fails: bool = False,
        install_writes_forbidden_asset: bool = False,
    ) -> None:
        self.commands: list[list[str]] = []
        self.dry_run_writes = dry_run_writes
        self.check_fails = check_fails
        self.install_writes_forbidden_asset = install_writes_forbidden_asset

    def __call__(self, command: list[object]) -> FakeCompletedProcess:
        rendered = [str(part) for part in command]
        self.commands.append(rendered)

        if rendered[1:4] == ["-m", "pip", "install"]:
            return FakeCompletedProcess(0, "installed\n", "")

        executable = Path(rendered[0]).name
        if executable != "hally-harness-engineering":
            return FakeCompletedProcess(1, "", "unexpected command\n")

        action = rendered[1]
        target = Path(rendered[2])
        if action == "install" and "--dry-run" in rendered:
            if self.dry_run_writes:
                (target / ".harness").mkdir(parents=True)
            return FakeCompletedProcess(0, "copy .harness/ARCHITECTURE.md\n", "")
        if action == "install":
            (target / ".harness").mkdir(parents=True, exist_ok=True)
            (target / ".harness" / "ARCHITECTURE.md").write_text("architecture\n", encoding="utf-8")
            if self.install_writes_forbidden_asset:
                forbidden = target / "harness-design" / "handoff.template.md"
                forbidden.parent.mkdir(parents=True)
                forbidden.write_text("source design leak\n", encoding="utf-8")
            return FakeCompletedProcess(0, "copied 1, pruned 0\n", "")
        if action == "check":
            if self.check_fails:
                return FakeCompletedProcess(1, "missing .harness/ARCHITECTURE.md\n", "")
            return FakeCompletedProcess(0, "ok\n", "")
        if action == "update":
            retired = target / ".harness" / "rules" / "install-rules.md"
            if retired.exists():
                retired.unlink()
            return FakeCompletedProcess(0, "copied 1, pruned 1\n", "")

        return FakeCompletedProcess(1, "", "unknown action\n")


def load_smoke_install_module():
    spec = importlib.util.spec_from_file_location("smoke_install", SMOKE_INSTALL)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {SMOKE_INSTALL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["version"]


def wheel_name(version: str) -> str:
    return f"hally_harness_engineering-{version}-py3-none-any.whl"


def prepare_dist(root: Path) -> Path:
    version = project_version()
    dist = root / "dist"
    dist.mkdir()
    (dist / wheel_name(version)).write_text("wheel placeholder\n", encoding="utf-8")
    return dist


def fake_artifact_checker(dist: Path, pyproject: Path) -> dict[str, str]:
    return {
        "package": "hally-harness-engineering",
        "version": project_version(),
        "wheel": wheel_name(project_version()),
    }


def fake_create_venv(path: Path) -> None:
    bin_dir = path / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").write_text("python\n", encoding="utf-8")
    (bin_dir / "hally-harness-engineering").write_text("cli\n", encoding="utf-8")


class ReleaseSmokeTest(unittest.TestCase):
    def test_smoke_installs_wheel_and_exercises_installed_cli(self) -> None:
        module = load_smoke_install_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = prepare_dist(root)
            runner = FakeRunner()

            result = module.run_smoke(
                dist,
                pyproject=PYPROJECT,
                temp_root=root / "smoke",
                runner=runner,
                create_venv=fake_create_venv,
                artifact_checker=fake_artifact_checker,
            )

            commands = [" ".join(command) for command in runner.commands]
            self.assertEqual(result["wheel"], wheel_name(project_version()))
            self.assertTrue(any(" -m pip install --no-deps " in command for command in commands))
            self.assertTrue(any("hally-harness-engineering install" in command and "--dry-run" in command for command in commands))
            self.assertTrue(any("hally-harness-engineering install" in command and "--dry-run" not in command for command in commands))
            self.assertTrue(any("hally-harness-engineering check" in command for command in commands))
            self.assertTrue(any("hally-harness-engineering update" in command for command in commands))
            self.assertTrue((root / "smoke" / "target" / ".harness" / "ARCHITECTURE.md").is_file())
            self.assertFalse((root / "smoke" / "target" / ".harness" / "rules" / "install-rules.md").exists())

    def test_smoke_fails_if_dry_run_writes_to_target(self) -> None:
        module = load_smoke_install_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = prepare_dist(root)

            with self.assertRaises(module.SmokeInstallError) as raised:
                module.run_smoke(
                    dist,
                    pyproject=PYPROJECT,
                    temp_root=root / "smoke",
                    runner=FakeRunner(dry_run_writes=True),
                    create_venv=fake_create_venv,
                    artifact_checker=fake_artifact_checker,
                )

            self.assertIn("dry-run wrote to target", str(raised.exception))

    def test_smoke_fails_when_installed_check_command_fails(self) -> None:
        module = load_smoke_install_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = prepare_dist(root)

            with self.assertRaises(module.SmokeInstallError) as raised:
                module.run_smoke(
                    dist,
                    pyproject=PYPROJECT,
                    temp_root=root / "smoke",
                    runner=FakeRunner(check_fails=True),
                    create_venv=fake_create_venv,
                    artifact_checker=fake_artifact_checker,
                )

            self.assertIn("command failed: hally-harness-engineering check", str(raised.exception))

    def test_smoke_fails_when_install_writes_forbidden_target_assets(self) -> None:
        module = load_smoke_install_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = prepare_dist(root)

            with self.assertRaises(module.SmokeInstallError) as raised:
                module.run_smoke(
                    dist,
                    pyproject=PYPROJECT,
                    temp_root=root / "smoke",
                    runner=FakeRunner(install_writes_forbidden_asset=True),
                    create_venv=fake_create_venv,
                    artifact_checker=fake_artifact_checker,
                )

            self.assertIn("install wrote forbidden target asset", str(raised.exception))
            self.assertIn("harness-design/handoff.template.md", str(raised.exception))

    def test_main_reports_smoke_checks(self) -> None:
        module = load_smoke_install_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = prepare_dist(root)
            module.run_command = FakeRunner()
            module.create_virtualenv = fake_create_venv
            module.check_artifacts = fake_artifact_checker
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = module.main([str(dist), "--temp-root", str(root / "smoke")])

            self.assertEqual(code, 0, stderr.getvalue())
            self.assertIn("wheel: " + wheel_name(project_version()), stdout.getvalue())
            self.assertIn("dry-run: no writes", stdout.getvalue())
            self.assertIn("install: .harness/ARCHITECTURE.md present", stdout.getvalue())
            self.assertIn("check: ok", stdout.getvalue())
            self.assertIn("update: retired asset pruned", stdout.getvalue())

    def test_install_lifecycle_documents_smoke_release_gate(self) -> None:
        text = INSTALL_DOC.read_text(encoding="utf-8")

        self.assertIn("installed-tool smoke testing", text)
        self.assertIn("python3 installer/release/smoke_install.py dist", text)
        self.assertIn("before TestPyPI/PyPI publication", text)


if __name__ == "__main__":
    unittest.main()
