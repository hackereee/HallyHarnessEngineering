# Harness Installer Lifecycle

This document defines the external installer handoff for putting Harness Engineering into a target repository. It is intentionally outside `.harness/` because installation is a bootstrap and distribution concern, not a runtime Harness workflow gate.

The runtime Harness framework begins after fixed assets are present in the target repository. Runtime truth sources remain `work/workflow-state.json`, active plan packages, task state, and project contracts.

## Distribution Goal

The intended package distribution path is a Python CLI published as `hally-harness-engineering`. After publication, users should install the tool with an isolated app installer:

```bash
pipx install hally-harness-engineering
```

or:

```bash
uv tool install hally-harness-engineering
```

The installed command is:

```bash
hally-harness-engineering install .
hally-harness-engineering update .
hally-harness-engineering check .
```

PyPI publishing and release workflow are defined in the release operation document. This lifecycle only defines the packageable installer boundary and runtime handoff.

Package releases must run installed-tool smoke testing before TestPyPI/PyPI publication:

```bash
python3 -m build
python3 installer/release/check_artifacts.py dist
python3 installer/release/smoke_install.py dist
```

The smoke gate installs the local wheel into a temporary virtual environment, runs the installed `hally-harness-engineering` command against a temporary target repository, verifies that `install --dry-run` writes nothing, confirms install/check success, and confirms `update` prunes retired installer assets. This is a package release gate, not a Harness runtime workflow gate.

Manual publication is defined in `.github/workflows/publish-python-package.yml`. Operator steps for Trusted Publisher setup, TestPyPI validation, PyPI promotion, install/upgrade commands, and yank/rollback recovery are documented in `docs/release/package-registry-release.md`.

## Ordered Installer Handoff

1. Release fixed Harness assets
   - Copy or update the fixed `.harness/` framework assets in the target repository.
   - Fixed assets include schemas, templates, rules, skills, scripts, tests, and `.harness/ARCHITECTURE.md`.
   - The installer must preserve existing `.harness/contracts/` and `work/` unless the user explicitly requests a destructive reset.
   - The installer must not copy the source repository's `work/`, root `AGENTS.md`, root `README.md`, or root business `ARCHITECTURE.md` into the target repository.

2. Run installer self-checks
   - Check the fixed asset manifest, template/schema presence, Python/jsonschema availability, Harness CLI help, and read-only Harness lint when the target shape allows it.
   - Self-check failures are installer failures, not project environment failures.
   - This step must not run a normal `session-start.py` bootstrap because target entrypoint integration and project contracts may still be missing.

3. Hand off to `project-init`
   - Use `.harness/skills/project-init/SKILL.md` after fixed assets are present.
   - `project-init` reads target agent entrypoints, performs semantic workflow conflict review, chooses the canonical entrypoint, and calls `init-project-entrypoint.py` to create or update the managed block.
   - `project-init` may recommend changes outside the managed block, but deterministic entrypoint writes own only the managed block.

4. Hand off to `project-env-contract`
   - Use `.harness/skills/project-env-contract/SKILL.md` to derive project environment facts from repository evidence and explicit user answers.
   - The default output is `.harness/contracts/project-contracts.json`.
   - `check-project-env.py` only validates and executes the declared contract; it must not infer project requirements from the repository.

5. Enter normal Harness workflow
   - Use `session-start.py` to validate or bootstrap runtime workflow state.
   - Use `check-project-env.py` to run declared project environment checks.
   - Starting a new workflow still goes through `start-workflow.py`.
   - State changes still go through `state-write.py`.

## Runtime Boundary

The installer does not become a Harness workflow gate. It must not write `work/workflow-state.json`, must not write `tasks.json`, must not create active plan packages, and must not consume backlog items.

Installed runtime tools keep their own boundaries:

- `project-init` integrates target entrypoints but does not write workflow runtime state.
- `project-env-contract` guides project contract creation but does not mark verification, review, or task completion.
- `session-start.py` remains a startup and audit tool, not an installer.
- `check-project-env.py` remains a contract runner, not a repository inference engine.

## Failure Handling

- Missing fixed `.harness/` assets: stop and return `HARNESS_ASSETS_MISSING`; run the installer before `project-init`.
- Entrypoint conflicts: report conflicts during `project-init`; do not normalize them silently.
- Missing `.harness/contracts/project-contracts.json`: report `NOT_CONFIGURED` from `check-project-env.py`; do not treat it as core installation failure.
- Existing `work/` state conflicts: follow `.harness/rules/session-start.md` and `.harness/rules/workflow-lifecycle.md`; installer and project-init must not infer or repair workflow state from prose.
