from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .manifest import AssetManifest, load_manifest, payload_root


class InstallMode(StrEnum):
    INSTALL = "install"
    UPDATE = "update"


@dataclass(frozen=True)
class Operation:
    action: str
    path: str


@dataclass(frozen=True)
class InstallResult:
    operations: tuple[Operation, ...]

    @property
    def copy_count(self) -> int:
        return sum(1 for operation in self.operations if operation.action == "copy")

    @property
    def prune_count(self) -> int:
        return sum(1 for operation in self.operations if operation.action == "prune")


@dataclass(frozen=True)
class CheckReport:
    ok: bool
    missing_assets: tuple[str, ...]


def normalize_target(target: Path) -> Path:
    return target.expanduser().resolve()


def is_under_preserve_path(asset: str, manifest: AssetManifest) -> bool:
    return any(asset.startswith(path) for path in manifest.preserve_paths)


def write_payload_asset(asset: str, target: Path) -> None:
    source = payload_root() / asset
    destination = target / asset
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    if asset.startswith(".harness/scripts/"):
        current_mode = destination.stat().st_mode
        os.chmod(destination, current_mode | 0o755)


def planned_copy_operations(target: Path, manifest: AssetManifest) -> list[Operation]:
    operations: list[Operation] = []
    for asset in manifest.fixed_assets:
        destination = target / asset
        if destination.exists() and is_under_preserve_path(asset, manifest):
            continue
        operations.append(Operation("copy", asset))
    return operations


def planned_prune_operations(target: Path, manifest: AssetManifest, mode: InstallMode) -> list[Operation]:
    if mode != InstallMode.UPDATE:
        return []
    return [
        Operation("prune", asset)
        for asset in manifest.retired_assets
        if (target / asset).exists()
    ]


def install_harness(
    target: Path,
    *,
    mode: InstallMode = InstallMode.INSTALL,
    dry_run: bool = False,
    manifest: AssetManifest | None = None,
) -> InstallResult:
    manifest = manifest or load_manifest()
    target = normalize_target(target)
    operations = (
        planned_copy_operations(target, manifest)
        + planned_prune_operations(target, manifest, mode)
    )

    if dry_run:
        return InstallResult(tuple(operations))

    target.mkdir(parents=True, exist_ok=True)
    for operation in operations:
        destination = target / operation.path
        if operation.action == "copy":
            write_payload_asset(operation.path, target)
        elif operation.action == "prune" and destination.exists():
            destination.unlink()

    return InstallResult(tuple(operations))


def check_harness(target: Path, *, manifest: AssetManifest | None = None) -> CheckReport:
    manifest = manifest or load_manifest()
    target = normalize_target(target)
    missing = tuple(
        asset
        for asset in manifest.fixed_assets
        if not (target / asset).is_file()
    )
    return CheckReport(ok=not missing, missing_assets=missing)
