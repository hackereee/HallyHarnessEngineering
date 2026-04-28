#!/usr/bin/env python3

from __future__ import annotations

import argparse
import configparser
import re
import sys
import tomllib
import zipfile
from email import policy
from email.parser import Parser
from pathlib import Path
from typing import Iterable


PACKAGE_NAME = "harness-engineering"
CONSOLE_SCRIPT = "harness-engineering"
CONSOLE_TARGET = "harness_engineering_installer.cli:main"
REQUIRED_DEPENDENCY = "jsonschema>=4.18"
PAYLOAD_PREFIX = "harness_engineering_installer/payload/.harness/"
REQUIRED_PAYLOAD_ARCHITECTURE = PAYLOAD_PREFIX + "ARCHITECTURE.md"
REQUIRED_PAYLOAD_CATEGORIES = (
    "schemas/",
    "scripts/",
    "templates/",
    "skills/",
    "rules/",
)


class ArtifactCheckError(Exception):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_project_metadata(pyproject: Path) -> dict:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactCheckError(f"missing pyproject {pyproject}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ArtifactCheckError(f"invalid pyproject {pyproject}: {exc}") from exc

    project = data.get("project")
    if not isinstance(project, dict):
        raise ArtifactCheckError("pyproject.toml missing [project]")
    return project


def filename_stem(package_name: str, version: str) -> str:
    normalized_name = re.sub(r"[-_.]+", "_", package_name).strip("_")
    return f"{normalized_name}-{version}"


def expected_artifacts(project: dict) -> tuple[str, str]:
    name = project.get("name")
    version = project.get("version")
    if name != PACKAGE_NAME:
        raise ArtifactCheckError(f"pyproject package name must be {PACKAGE_NAME}")
    if not isinstance(version, str) or not version:
        raise ArtifactCheckError("pyproject project.version must be a non-empty string")

    stem = filename_stem(name, version)
    return f"{stem}.tar.gz", f"{stem}-py3-none-any.whl"


def distribution_artifacts(dist_dir: Path) -> set[str]:
    if not dist_dir.is_dir():
        raise ArtifactCheckError(f"dist directory not found: {dist_dir}")
    return {
        path.name
        for path in dist_dir.iterdir()
        if path.is_file() and (path.name.endswith(".tar.gz") or path.suffix == ".whl")
    }


def verify_dist_files(dist_dir: Path, project: dict) -> tuple[Path, Path]:
    expected_sdist, expected_wheel = expected_artifacts(project)
    artifacts = distribution_artifacts(dist_dir)
    expected = {expected_sdist, expected_wheel}

    if expected_sdist not in artifacts:
        raise ArtifactCheckError(f"missing sdist {expected_sdist}")
    if expected_wheel not in artifacts:
        raise ArtifactCheckError(f"missing wheel {expected_wheel}")

    unexpected = sorted(artifacts - expected)
    if unexpected:
        raise ArtifactCheckError("unexpected distribution artifact: " + ", ".join(unexpected))

    return dist_dir / expected_sdist, dist_dir / expected_wheel


def read_wheel_text(wheel: zipfile.ZipFile, suffix: str) -> str:
    matches = [name for name in wheel.namelist() if name.endswith(suffix)]
    if not matches:
        raise ArtifactCheckError(f"wheel missing {suffix}")
    if len(matches) > 1:
        raise ArtifactCheckError(f"wheel has multiple {suffix} files")
    return wheel.read(matches[0]).decode("utf-8")


def verify_metadata(wheel: zipfile.ZipFile) -> str:
    text = read_wheel_text(wheel, ".dist-info/METADATA")
    metadata = Parser(policy=policy.default).parsestr(text)

    name = metadata.get("Name")
    if name != PACKAGE_NAME:
        raise ArtifactCheckError(f"missing package metadata Name {PACKAGE_NAME}")

    dependencies = [value.strip() for value in metadata.get_all("Requires-Dist", [])]
    if REQUIRED_DEPENDENCY not in dependencies:
        raise ArtifactCheckError(f"missing dependency {REQUIRED_DEPENDENCY}")

    return name


def verify_entry_point(wheel: zipfile.ZipFile) -> None:
    try:
        text = read_wheel_text(wheel, ".dist-info/entry_points.txt")
    except ArtifactCheckError as exc:
        raise ArtifactCheckError(f"missing console script {CONSOLE_SCRIPT} = {CONSOLE_TARGET}") from exc
    parser = configparser.ConfigParser()
    parser.read_string(text)

    target = ""
    if parser.has_section("console_scripts") and parser.has_option("console_scripts", CONSOLE_SCRIPT):
        target = parser.get("console_scripts", CONSOLE_SCRIPT).strip()

    if target != CONSOLE_TARGET:
        raise ArtifactCheckError(f"missing console script {CONSOLE_SCRIPT} = {CONSOLE_TARGET}")


def verify_payload(wheel: zipfile.ZipFile) -> None:
    names = set(wheel.namelist())
    if REQUIRED_PAYLOAD_ARCHITECTURE not in names:
        raise ArtifactCheckError(f"missing payload asset {REQUIRED_PAYLOAD_ARCHITECTURE}")

    for category in REQUIRED_PAYLOAD_CATEGORIES:
        prefix = PAYLOAD_PREFIX + category
        if not any(name.startswith(prefix) and not name.endswith("/") for name in names):
            raise ArtifactCheckError(f"missing payload asset under {prefix}")


def check_wheel(wheel_path: Path) -> None:
    try:
        with zipfile.ZipFile(wheel_path) as wheel:
            verify_metadata(wheel)
            verify_entry_point(wheel)
            verify_payload(wheel)
    except zipfile.BadZipFile as exc:
        raise ArtifactCheckError(f"invalid wheel {wheel_path.name}: {exc}") from exc


def check_artifacts(dist_dir: Path, pyproject: Path) -> dict[str, str]:
    project = read_project_metadata(pyproject)
    sdist, wheel = verify_dist_files(dist_dir, project)
    check_wheel(wheel)
    return {
        "package": PACKAGE_NAME,
        "version": str(project["version"]),
        "wheel": wheel.name,
        "sdist": sdist.name,
        "entry_point": f"{CONSOLE_SCRIPT} = {CONSOLE_TARGET}",
        "dependency": REQUIRED_DEPENDENCY,
        "payload": "architecture, schemas, scripts, templates, skills, rules",
    }


def print_report(report: dict[str, str]) -> None:
    print(f"package: {report['package']}")
    print(f"version: {report['version']}")
    print(f"wheel: {report['wheel']}")
    print(f"sdist: {report['sdist']}")
    print(f"entry point: {report['entry_point']}")
    print(f"dependency: {report['dependency']}")
    print(f"payload: {report['payload']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect built harness-engineering release artifacts")
    parser.add_argument("dist", type=Path, help="Directory containing built wheel and source distribution")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=repo_root() / "pyproject.toml",
        help="pyproject.toml containing package name and version",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = check_artifacts(args.dist, args.pyproject)
    except ArtifactCheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
