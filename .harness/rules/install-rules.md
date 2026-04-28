# install-rules.md

Harness installation is a two-layer lifecycle: deterministic framework asset release first, semantic target project integration second. This rule documents the handoff between the installer, `project-init`, `project-env-contract`, and workflow startup tools.

The core judgment is strict:

- scripts handle deterministic, repeatable, auditable installation steps;
- Agents handle semantic review, target entrypoint conflict analysis, and project environment contract derivation;
- neither layer may bypass Harness runtime write gateways.

## Ordered Installation Lifecycle

1. install-harness releases fixed `.harness/` assets
   - The installer releases fixed framework assets into the target repository.
   - It may create or update `.harness/ARCHITECTURE.md`, `.harness/rules/`, `.harness/schemas/`, `.harness/templates/`, `.harness/scripts/`, `.harness/skills/`, and `.harness/tests/`.
   - It must preserve existing `.harness/contracts/` and `work/` unless the user explicitly requests a destructive reset.
   - It must not copy the source repository's `work/`, root `AGENTS.md`, root `README.md`, or root business `ARCHITECTURE.md` into the target repository.

2. Harness core self-check
   - The installer runs deterministic core checks before handing control to the Agent.
   - Minimum checks: required asset manifest, template/schema presence, Python/jsonschema availability, Harness CLI help, and read-only Harness lint when the target shape allows it.
   - This step must not run a normal `session-start.py` bootstrap yet, because target entrypoint integration and project contracts may still be missing.
   - Self-check failures are installer failures, not project environment failures.

3. Agent runs `project-init`
   - The Agent reads all detected target entrypoints such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, Copilot instructions, and editor rules.
   - It evaluates workflow conflicts and chooses the canonical entrypoint.
   - It calls `init-project-entrypoint.py --write` or `--create` to write the Harness managed block.
   - `project-init` must not merge freeform entrypoint prose. It may recommend prose changes outside markers, but the deterministic write only owns the managed block.
   - semantic conflict judgment belongs to `project-init`, not to the installer or `init-project-entrypoint.py`.

4. Agent runs `project-env-contract`
   - The Agent derives project environment facts from repository evidence and explicit user answers.
   - project environment facts belong in `.harness/contracts/project-contracts.json`.
   - `check-project-env.py` only validates and executes the declared contract; it must not infer project requirements from the repository.
   - A missing project contract is `NOT_CONFIGURED`, not a broken Harness core installation.

5. Enter the actual workflow
   - After entrypoint integration and project contract handling, run `session-start.py` or `check-project-env.py` depending on the next action.
   - Use `session-start.py` to validate or bootstrap the current Harness workflow state.
   - Use `check-project-env.py` to execute declared project environment checks.
   - Starting a new workflow still goes through `start-workflow.py`; state changes still go through `state-write.py`.

## Write Boundaries

`install-harness` may write fixed Harness framework assets, but it must not write `workflow-state.json`, must not write `tasks.json`, must not create active plan packages, and must not consume backlog items.

`project-init` may select or create an entrypoint and call `init-project-entrypoint.py`, but it must not write runtime state, must not create tasks, and must not add project-specific environment checks to `session-start.py`.

`project-env-contract` may guide creation or revision of `.harness/contracts/project-contracts.json`, but it must not mark environment checks as workflow verification, review, or task completion.

`session-start.py` remains a startup and audit tool. It validates Harness core assets and workflow state shape, but it is not the installer and not the project environment checker.

## Failure Handling

- Missing fixed `.harness/` assets: stop and return `HARNESS_ASSETS_MISSING`; run `install-harness` before `project-init`.
- Entrypoint conflicts: report conflicts during `project-init`; do not normalize them silently.
- Missing `.harness/contracts/project-contracts.json`: report `NOT_CONFIGURED` from `check-project-env.py`; do not treat it as core installation failure.
- Existing `work/` state conflicts: follow `session-start.md` and `workflow-lifecycle.md`; installer and project-init must not infer or repair workflow state from prose.
