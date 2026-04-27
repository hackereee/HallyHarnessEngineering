# PLAN-004: Add Project Environment Contracts Runner

## Background and Goal

`project-init` should not output a free-standing project check script as the source of truth because generated scripts drift from repository facts and contracts. Add a first-class project environment contract and a generic checker runner so the contract remains the truth source and the script only executes declared checks.

## Scope

- Add a machine-checkable project contracts schema and template.
- Add a deterministic generic runner that reads a project contracts file and executes declared command or probe checks.
- Wire the runner into Harness assets, CLI, and project-init documentation without adding project-specific checks to `session-start.py`.
- Add focused regression tests for schema, runner behavior, CLI dispatch, required-asset gating, and documentation.

## Non-Scope

- Do not generate project-specific contracts for this repository.
- Do not run project environment checks during `session-start.py`.
- Do not add project runtime facts to workflow state, task state, or Harness core schemas.
- Do not create custom project adapters in this plan.
- Do not split contracts into multiple files until the single-file shape proves insufficient.

## Implementation Direction

Use `.harness/templates/project-contracts.template.json` as the sample contract and `.harness/schemas/project-contracts.schema.json` as the truth-source schema. Add `.harness/scripts/check-project-env.py` as a generic runner that validates the contract and executes `environmentChecks` in a deterministic way. The runner must not infer requirements from the repository and must not modify workflow or task state.

## File Boundaries

- Create: `.harness/schemas/project-contracts.schema.json`
- Create: `.harness/templates/project-contracts.template.json`
- Create: `.harness/tests/test_project_contracts_schema.py`
- Create: `.harness/scripts/check-project-env.py`
- Create: `.harness/tests/test_check_project_env.py`
- Modify: `.harness/scripts/harness`
- Modify: `.harness/tests/test_harness_cli.py`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/tests/test_session_start.py`
- Modify: `.harness/skills/project-init/SKILL.md`
- Modify: `.harness/tests/test_project_init_skill.py`
- Modify: `harness-design/architecture.md`

## Task Decomposition

The plan first creates the contract schema/template because the runner must consume a declared contract instead of inventing facts. The second task implements the runner and its behavior tests. The final task wires the new Harness assets and documents the boundary now that the assets exist, avoiding the same self-blocking order issue fixed in PLAN-003.

## Verification Strategy

Run schema tests after contract changes, runner tests after script changes, and session/CLI/project-init tests after wiring. Finish with full Harness unittest discovery, lint, and workflow-state validation.

## Risks and Open Questions

- Risk: The runner could become a second source of truth if it hard-codes project checks; tests must assert it only uses contract data.
- Risk: Adding the runner to `session-start.py` before the file exists would self-block lifecycle preflight; this plan wires required assets only after the script and schema exist.
- Open questions: None for the first single-file contract shape.

## Task Contracts

<a id="task-001-define-project-contracts"></a>

### TASK-001: Define project contracts

Goal: Add the schema and template for project environment contracts.

Files:
- Create: `.harness/schemas/project-contracts.schema.json`
- Create: `.harness/templates/project-contracts.template.json`
- Create: `.harness/tests/test_project_contracts_schema.py`

Depends on: []

Acceptance:
- `project-contracts.schema.json` validates `project-contracts.template.json`.
- The schema contains `projectProfile`, `commandRegistry`, and `environmentChecks`.
- Every environment check has a stable id, description, evidence source, severity, and either a command reference or a deterministic probe.
- Severity is restricted to `blocking` or `warning`.
- Adapter fallback is modeled as contract metadata, not executable truth.

Verification:
- Run: `python3 .harness/tests/test_project_contracts_schema.py`
- Check: the template includes project profile, command registry, environment checks, blocking/warning severity, evidence source, and adapter fallback metadata.

<a id="task-002-implement-project-env-runner"></a>

### TASK-002: Implement project env runner

Goal: Add a generic runner that validates and executes project contract checks.

Files:
- Create: `.harness/scripts/check-project-env.py`
- Create: `.harness/tests/test_check_project_env.py`

Depends on: [TASK-001]

Acceptance:
- The runner validates the contract against `project-contracts.schema.json` before execution.
- The runner executes command checks by resolving `commandRef` through `commandRegistry`.
- The runner supports deterministic probes for file existence and executable availability.
- The runner exits non-zero for failed blocking checks and exits zero when only warning checks fail.
- The runner output includes check ids, severity, result, and evidence source.
- The runner does not write `workflow-state.json`, `tasks.json`, or active plan files.

Verification:
- Run: `python3 .harness/tests/test_check_project_env.py`
- Check: test fixtures prove blocking failure, warning-only success, commandRef execution, and schema rejection.

<a id="task-003-wire-project-env-runner"></a>

### TASK-003: Wire project env runner

Goal: Expose and document the project contracts runner without turning it into session startup behavior.

Files:
- Modify: `.harness/scripts/harness`
- Modify: `.harness/tests/test_harness_cli.py`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/tests/test_session_start.py`
- Modify: `.harness/skills/project-init/SKILL.md`
- Modify: `.harness/tests/test_project_init_skill.py`
- Modify: `harness-design/architecture.md`

Depends on: [TASK-001, TASK-002]

Acceptance:
- `.harness/scripts/harness` exposes a `check-project-env` subcommand.
- `session-start.py` requires the runner, schema, and template as Harness assets but does not execute project environment checks.
- `project-init` names the concrete output contract path and the runner command while preserving the contract-first rule.
- `architecture.md` documents project contracts and the generic runner as separate from workflow state and session startup.

Verification:
- Run: `python3 .harness/tests/test_harness_cli.py`
- Run: `python3 .harness/tests/test_session_start.py`
- Run: `python3 .harness/tests/test_project_init_skill.py`
- Run: `python3 .harness/scripts/lint-harness.py --root .`
- Check: documentation states contracts are the truth source and the runner does not replace `session-start.py`.
