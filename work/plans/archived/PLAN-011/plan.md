# PLAN-011: Packageable Harness Installer CLI

## Background and Goal

Make Harness Engineering installable as a Python CLI package so a user can install or update Harness assets in a target repository with one command after installing the tool through PyPI-compatible tooling such as `pipx` or `uv tool install`.

## Scope

- Add Python package metadata for a CLI distribution named `harness-engineering`.
- Define a fixed asset manifest for runtime `.harness/` assets and installer-owned retired assets.
- Bundle fixed `.harness/` assets as package resources.
- Implement `harness-engineering install`, `harness-engineering update`, and `harness-engineering check`.
- Preserve target `work/` and `.harness/contracts/` data.
- Keep installer behavior separate from Harness workflow gates.

## Non-Scope

- Do not publish to PyPI in this plan.
- Do not add GitHub Actions release automation in this plan.
- Do not run `session-start.py` automatically after install.
- Do not create target project entrypoints automatically beyond copying fixed Harness assets.
- Do not modify target root `AGENTS.md`, `README.md`, or `ARCHITECTURE.md`.

## Implementation Direction

Use a standard Python package with a `pyproject.toml` console script entry point. Keep installer code under `src/harness_engineering_installer/`, fixed assets under package resources, and installer tests under `installer/tests/`. The CLI should be safe by default: dry-run must be available, runtime state must be preserved, and updates must only remove explicitly retired fixed assets listed in the manifest.

## File Boundaries

- Create: `pyproject.toml`
- Create: `src/harness_engineering_installer/__init__.py`
- Create: `src/harness_engineering_installer/assets-manifest.json`
- Create: `src/harness_engineering_installer/manifest.py`
- Create: `src/harness_engineering_installer/installer.py`
- Create: `src/harness_engineering_installer/cli.py`
- Create: `src/harness_engineering_installer/payload/.harness/**`
- Modify: `installer/install-lifecycle.md`
- Modify: `README.md`
- Test: `installer/tests/test_asset_manifest.py`
- Test: `installer/tests/test_installer_engine.py`
- Test: `installer/tests/test_installer_cli.py`
- Test: `installer/tests/test_install_lifecycle.py`

## Task Decomposition

The plan is split by release boundary. First define package metadata, manifest, and bundled assets so the installer has a deterministic source of truth. Then implement the safe copy/update engine. Finally wire the CLI and packaging-facing documentation.

## Verification Strategy

Use unit tests for manifest consistency, dry-run behavior, preservation rules, retired asset pruning, and CLI command behavior. Run full installer tests, full `.harness/tests`, Harness lint, workflow-state validation, and `git diff --check`. If the Python `build` module is available, verify `python3 -m build`; otherwise record the missing build module as a packaging follow-up.

## Architecture Impact

- Expected target project architecture impact: root `ARCHITECTURE.md` remains unchanged. Installing Harness assets must not write target business architecture.
- Expected Harness framework architecture impact: `.harness/ARCHITECTURE.md` remains runtime-framework focused. Installer package architecture is documented in `installer/install-lifecycle.md` and packaging metadata, not inside `.harness/` runtime rules.
- This is a workflow gate record, not a standalone task.

## Risks and Open Questions

- Risk: Bundling `.harness/` assets inside the Python package can drift from source `.harness/` files. The manifest test must compare source assets and packaged payload files.
- Risk: Update mode can delete user files if pruning is broad. Only explicitly listed retired fixed assets may be removed.
- Risk: PyPI package name may already be unavailable. This plan creates package metadata; actual publishing and naming confirmation remain a later release task.
- Open questions: None blocking for a local packageable CLI skeleton.

## Plan Review Gate

Status: passed
Reviewer: codex
Reviewed At: 2026-04-28T13:40:00+08:00

Checks:
- Scope, non-scope, file boundaries, dependencies, acceptance, and verification are reviewable.
- Package publishing is separated from local packageable CLI implementation.
- Installer does not become a workflow gate and does not write runtime state.
- Testing and review remain workflow gates, not standalone tasks.

Findings:
- No blocking findings.

## Task Contracts

<a id="task-001-package-metadata-assets"></a>

### TASK-001: Package metadata and bundled assets

Goal: Define the Python package boundary, manifest, and bundled fixed Harness assets.

Files:
- Create: `pyproject.toml`
- Create: `src/harness_engineering_installer/__init__.py`
- Create: `src/harness_engineering_installer/assets-manifest.json`
- Create: `src/harness_engineering_installer/manifest.py`
- Create: `src/harness_engineering_installer/payload/.harness/**`
- Test: `installer/tests/test_asset_manifest.py`

Depends on: []

Acceptance:
- `pyproject.toml` declares package name `harness-engineering` and console script `harness-engineering`.
- `assets-manifest.json` lists fixed `.harness/` assets, preserve paths, forbidden root files, and retired assets.
- The manifest excludes `work/`, root `AGENTS.md`, root `README.md`, root `ARCHITECTURE.md`, and Python cache files.
- Every manifest fixed asset exists in the package payload.
- Every source `.harness/` fixed asset is represented in the manifest or explicitly excluded.

Verification:
- Run: `python3 installer/tests/test_asset_manifest.py`
- Check: `rg -n "\"work/\"|\"AGENTS.md\"|\"README.md\"|\"ARCHITECTURE.md\"" src/harness_engineering_installer/assets-manifest.json` returns no forbidden fixed asset entries.

<a id="task-002-safe-installer-engine"></a>

### TASK-002: Safe installer engine

Goal: Implement deterministic install/update/check behavior from the bundled manifest.

Files:
- Create: `src/harness_engineering_installer/installer.py`
- Modify: `src/harness_engineering_installer/manifest.py`
- Test: `installer/tests/test_installer_engine.py`

Depends on: [TASK-001]

Acceptance:
- Dry-run reports planned copy/prune operations without writing the target directory.
- Install copies only manifest fixed assets into the target repository.
- Install preserves existing `work/` and `.harness/contracts/project-contracts.json`.
- Install never writes root `AGENTS.md`, `README.md`, or `ARCHITECTURE.md`.
- Update removes only manifest-listed retired assets.
- Check reports missing fixed assets without mutating the target repository.

Verification:
- Run: `python3 installer/tests/test_installer_engine.py`
- Check: fixture target keeps pre-existing `work/workflow-state.json` and `.harness/contracts/project-contracts.json` contents unchanged.

<a id="task-003-cli-and-packaging-docs"></a>

### TASK-003: CLI and packaging docs

Goal: Expose install/update/check as a package CLI and document the one-command installation path.

Files:
- Create: `src/harness_engineering_installer/cli.py`
- Modify: `installer/install-lifecycle.md`
- Modify: `README.md`
- Test: `installer/tests/test_installer_cli.py`
- Test: `installer/tests/test_install_lifecycle.py`

Depends on: [TASK-001, TASK-002]

Acceptance:
- `harness-engineering install <target> --dry-run` prints planned operations and writes nothing.
- `harness-engineering install <target>` installs bundled fixed assets.
- `harness-engineering update <target>` installs fixed assets and prunes manifest-listed retired assets.
- `harness-engineering check <target>` returns non-zero when fixed assets are missing.
- Docs mention `pipx install harness-engineering` and `uv tool install harness-engineering` as intended distribution paths.
- Docs state that PyPI publishing and release workflow are future release tasks.

Verification:
- Run: `python3 installer/tests/test_installer_cli.py`
- Run: `python3 installer/tests/test_install_lifecycle.py`
- Run: `python3 -m unittest discover -s installer/tests -p 'test_*.py'`
- Check: `python3 -m build` succeeds if the `build` module is installed.
