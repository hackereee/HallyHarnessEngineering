from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class AssetManifest:
    schema_version: int
    fixed_assets: tuple[str, ...]
    preserve_paths: tuple[str, ...]
    forbidden_root_files: tuple[str, ...]
    retired_assets: tuple[str, ...]


def package_root() -> resources.abc.Traversable:
    return resources.files("harness_engineering_installer")


def payload_root() -> resources.abc.Traversable:
    return package_root() / "payload"


def manifest_path() -> resources.abc.Traversable:
    return package_root() / "assets-manifest.json"


def load_manifest() -> AssetManifest:
    raw = json.loads(manifest_path().read_text(encoding="utf-8"))
    return AssetManifest(
        schema_version=raw["schemaVersion"],
        fixed_assets=tuple(raw["fixedAssets"]),
        preserve_paths=tuple(raw["preservePaths"]),
        forbidden_root_files=tuple(raw["forbiddenRootFiles"]),
        retired_assets=tuple(raw["retiredAssets"]),
    )


def load_manifest_from_path(path: Path) -> AssetManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return AssetManifest(
        schema_version=raw["schemaVersion"],
        fixed_assets=tuple(raw["fixedAssets"]),
        preserve_paths=tuple(raw["preservePaths"]),
        forbidden_root_files=tuple(raw["forbiddenRootFiles"]),
        retired_assets=tuple(raw["retiredAssets"]),
    )
