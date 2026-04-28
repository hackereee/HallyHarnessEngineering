#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Callable, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_artifacts import check_artifacts, repo_root  # noqa: E402


RETIRED_ASSET = Path(".harness") / "rules" / "install-rules.md"
FORBIDDEN_TARGET_ASSETS = (
    Path("harness-design"),
    Path("installer") / "install-lifecycle.md",
    Path("handoff.template.md"),
)


class SmokeInstallError(Exception):
    pass


def create_virtualenv(path: Path) -> None:
    venv.EnvBuilder(with_pip=True, clear=True).create(path)


def virtualenv_bin(path: Path) -> Path:
    return path / ("Scripts" if os.name == "nt" else "bin")


def run_command(command: list[object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        text=True,
        capture_output=True,
    )


def command_label(command: list[object]) -> str:
    rendered = [str(part) for part in command]
    executable = Path(rendered[0]).name if rendered else "<empty>"
    if executable == "hally-harness-engineering" and len(rendered) > 1:
        return f"hally-harness-engineering {rendered[1]}"
    if len(rendered) >= 4 and rendered[1:4] == ["-m", "pip", "install"]:
        return "python -m pip install"
    return " ".join(rendered)


def run_checked(command: list[object], runner: Callable[[list[object]], object]) -> object:
    result = runner(command)
    returncode = getattr(result, "returncode", None)
    if returncode != 0:
        stdout = getattr(result, "stdout", "")
        stderr = getattr(result, "stderr", "")
        detail = (stdout or "") + (stderr or "")
        message = f"command failed: {command_label(command)}"
        if detail.strip():
            message += f"\n{detail.strip()}"
        raise SmokeInstallError(message)
    return result


def ensure_no_dry_run_write(target: Path) -> None:
    if (target / ".harness").exists():
        raise SmokeInstallError("dry-run wrote to target")


def ensure_architecture_installed(target: Path) -> None:
    if not (target / ".harness" / "ARCHITECTURE.md").is_file():
        raise SmokeInstallError("install did not create .harness/ARCHITECTURE.md")


def ensure_forbidden_target_assets_absent(target: Path) -> None:
    leaked: list[str] = []
    for relative in FORBIDDEN_TARGET_ASSETS:
        path = target / relative
        if not path.exists():
            continue
        if path.is_dir():
            children = sorted(child for child in path.rglob("*") if child.is_file())
            if children:
                leaked.extend(child.relative_to(target).as_posix() for child in children)
            else:
                leaked.append(relative.as_posix())
        else:
            leaked.append(relative.as_posix())
    if leaked:
        raise SmokeInstallError("install wrote forbidden target asset: " + ", ".join(leaked))


def ensure_retired_asset_pruned(target: Path) -> None:
    if (target / RETIRED_ASSET).exists():
        raise SmokeInstallError("update did not prune .harness/rules/install-rules.md")


def run_smoke(
    dist: Path,
    *,
    pyproject: Path | None = None,
    temp_root: Path | None = None,
    runner: Callable[[list[object]], object] | None = None,
    create_venv: Callable[[Path], None] | None = None,
    artifact_checker: Callable[[Path, Path], dict[str, str]] | None = None,
) -> dict[str, str]:
    resolved_pyproject = pyproject or repo_root() / "pyproject.toml"
    command_runner = runner or run_command
    venv_creator = create_venv or create_virtualenv
    resolved_artifact_checker = artifact_checker or check_artifacts
    report = resolved_artifact_checker(dist, resolved_pyproject)
    wheel_name = report["wheel"]
    wheel = dist / wheel_name
    if not wheel.is_file():
        raise SmokeInstallError(f"wheel not found after artifact inspection: {wheel}")

    if temp_root is None:
        with tempfile.TemporaryDirectory(prefix="harness-release-smoke-") as tmp:
            return run_smoke(
                dist,
                pyproject=resolved_pyproject,
                temp_root=Path(tmp),
                runner=command_runner,
                create_venv=venv_creator,
                artifact_checker=resolved_artifact_checker,
            )

    temp_root.mkdir(parents=True, exist_ok=True)
    venv_dir = temp_root / "venv"
    target = temp_root / "target"
    venv_creator(venv_dir)

    bin_dir = virtualenv_bin(venv_dir)
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    cli = bin_dir / ("hally-harness-engineering.exe" if os.name == "nt" else "hally-harness-engineering")

    # Dependency metadata is checked by check_artifacts.py; smoke keeps the install local.
    run_checked([python, "-m", "pip", "install", "--no-deps", wheel], command_runner)
    run_checked([cli, "install", target, "--dry-run"], command_runner)
    ensure_no_dry_run_write(target)

    run_checked([cli, "install", target], command_runner)
    ensure_architecture_installed(target)
    ensure_forbidden_target_assets_absent(target)

    run_checked([cli, "check", target], command_runner)

    retired = target / RETIRED_ASSET
    retired.parent.mkdir(parents=True, exist_ok=True)
    retired.write_text("retired install rules\n", encoding="utf-8")
    run_checked([cli, "update", target], command_runner)
    ensure_retired_asset_pruned(target)
    ensure_forbidden_target_assets_absent(target)

    return {
        "wheel": wheel_name,
        "venv": str(venv_dir),
        "target": str(target),
        "dry_run": "no writes",
        "install": ".harness/ARCHITECTURE.md present",
        "check": "ok",
        "update": "retired asset pruned",
    }


def print_report(report: dict[str, str]) -> None:
    print(f"wheel: {report['wheel']}")
    print(f"venv: {report['venv']}")
    print(f"target: {report['target']}")
    print(f"dry-run: {report['dry_run']}")
    print(f"install: {report['install']}")
    print(f"check: {report['check']}")
    print(f"update: {report['update']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test the built hally-harness-engineering wheel")
    parser.add_argument("dist", type=Path, help="Directory containing built wheel and source distribution")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=repo_root() / "pyproject.toml",
        help="pyproject.toml containing package name and version",
    )
    parser.add_argument(
        "--temp-root",
        type=Path,
        default=None,
        help="Optional temporary root to use for the smoke environment",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = run_smoke(args.dist, pyproject=args.pyproject, temp_root=args.temp_root)
    except (SmokeInstallError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
