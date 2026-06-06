# PLAN-013: Standardize .harness Human-Facing Language to English

## Background and Goal

Source backlog: BL-007 (`chat:2026-04-29-harness-language-standardization`).

The `.harness` framework currently mixes English and Chinese across architecture documentation, rules, templates, schemas, script comments, diagnostics, and test expectations. This plan standardizes human-facing Harness framework assets to English while preserving the established Harness lifecycle, schema, script gateway, and workflow gate behavior.

## Scope

- Normalize `.harness` architecture, rule, skill, template, and schema prose to English.
- Normalize `.harness/scripts` module docstrings, comments, CLI help, diagnostics, and emitted user-facing messages to English.
- Update related `.harness/tests` expectations and add a regression guard for language standardization.
- Preserve Harness runtime boundaries: scripts remain deterministic gateways, `workflow-state.json` writes remain behind `state-write.py`, and `tasks.json` writes remain behind `update-task.py` or `materialize-tasks.py`.

## Non-Scope

- Do not translate root `AGENTS.md`, root `README.md`, root `ARCHITECTURE.md`, or any non-`.harness` project document.
- Do not change Harness task lifecycle semantics, phase transition rules, schema shape, task review thresholds, or script side effects.
- Do not model testing, review, backlog consumption, commit, handoff, or architecture impact as standalone delivery tasks.
- Do not hand-edit generated `tasks.json` runtime state.

## Implementation Direction

Treat this as an L3 decomposed Harness framework cleanup because it touches the contract layer, script layer, and regression suite. Work in dependency order: first normalize static framework contracts and documentation, then normalize scripts and paired expectations, then add a repository-level language guard and run the broader Harness regression set. Any remaining non-English text inside `.harness` must be treated as a blocking finding unless it is a deliberate compatibility fixture with explicit test coverage and a documented reason.

## File Boundaries

- Modify: `.harness/ARCHITECTURE.md`
- Modify: `.harness/rules/`
- Modify: `.harness/skills/`
- Modify: `.harness/templates/`
- Modify: `.harness/schemas/`
- Modify: `.harness/scripts/init-project-entrypoint.py`
- Modify: `.harness/scripts/`
- Modify: `.harness/tests/`
- Modify: `src/harness_engineering_installer/payload/.harness/`
- Test: `installer/tests/`
- Create: `.harness/tests/test_language_standardization.py`

## Task Decomposition

The work is split by artifact ownership. Entrypoint managed block versioning and gateway mapping comes first because it changes fixed asset contracts and the installer payload. Static contracts and prose follow because scripts and tests refer to the same terms. Script diagnostics and behavior expectations come after that. A final regression guard and full verification pass closes the plan.

## Verification Strategy

Each task must run the focused tests for its touched artifact family. The final task must run the broader Harness regression set and a language scan over `.harness`. Verification evidence belongs in task `verification`, session audit, and review summaries; it must not be represented as a separate task.

## Architecture Impact

- Expected target project architecture impact: root `ARCHITECTURE.md` should remain unchanged because this work only changes the Harness framework assets under `.harness`.
- Expected Harness framework architecture impact: `.harness/ARCHITECTURE.md`, rules, templates, schemas, scripts, skills, and tests are expected to change only for English normalization and regression coverage. Lifecycle semantics and directory responsibilities must remain unchanged.
- This is a workflow gate record, not a standalone task. Any architecture documentation edit is part of the affected deliverable task.

## Risks and Open Questions

- Risk: A naive text replacement can alter script behavior, especially validation heuristics and test fixtures. The implementation must distinguish user-facing diagnostics from intentional compatibility data.
- Risk: Some tests assert exact diagnostic text. Script and test changes must land in the same task boundary when needed.
- Open questions: None blocking. The backlog already defines the target language and scope.

## Plan Review Gate

Status: passed
Reviewer: harness-reviewer
Reviewed At: 2026-04-29T07:04:17+08:00

Checks:
- Scope, non-scope, file boundaries, dependencies, acceptance, and verification are reviewable.
- Task contracts are parseable and contain no testing-only or review-only tasks.
- Architecture Impact is recorded as a gate, not a standalone task.
- Testing and review remain workflow gates, not standalone tasks.
- The plan does not require direct writes to `workflow-state.json` or hand-authored `tasks.json`.

Findings:
- No blocking findings.

## Task Contracts

<a id="task-001-bump-entrypoint-managed-block-version"></a>

### TASK-001: Bump entrypoint managed block version

Goal: Bump the Harness entrypoint managed block to v2 and make the block map new workflow start and backlog consumption to their deterministic gateways.

Files:
- Modify: `.harness/templates/entrypoint-managed-block.template.md`
- Modify: `.harness/scripts/init-project-entrypoint.py`
- Modify: `.harness/schemas/project-entrypoints.schema.json`
- Modify: `.harness/templates/project-entrypoints.template.json`
- Modify: `.harness/skills/project-init/SKILL.md`
- Modify: `.harness/tests/test_init_project_entrypoint.py`
- Modify: `.harness/tests/test_project_entrypoints_schema.py`
- Modify: `.harness/tests/test_project_init_skill.py`
- Modify: `src/harness_engineering_installer/payload/.harness/templates/entrypoint-managed-block.template.md`
- Modify: `src/harness_engineering_installer/payload/.harness/scripts/init-project-entrypoint.py`
- Modify: `src/harness_engineering_installer/payload/.harness/schemas/project-entrypoints.schema.json`
- Modify: `src/harness_engineering_installer/payload/.harness/templates/project-entrypoints.template.json`
- Modify: `src/harness_engineering_installer/payload/.harness/skills/project-init/SKILL.md`
- Modify: `src/harness_engineering_installer/payload/.harness/ARCHITECTURE.md`
- Modify: `src/harness_engineering_installer/payload/.harness/rules/archive-rules.md`
- Modify: `src/harness_engineering_installer/payload/.harness/scripts/archive-plan.py`
- Modify: `src/harness_engineering_installer/payload/.harness/tests/test_init_project_entrypoint.py`
- Modify: `src/harness_engineering_installer/payload/.harness/tests/test_project_entrypoints_schema.py`
- Modify: `src/harness_engineering_installer/payload/.harness/tests/test_project_init_skill.py`
- Modify: `src/harness_engineering_installer/payload/.harness/tests/test_archive_plan.py`
- Test: `.harness/tests/test_init_project_entrypoint.py`
- Test: `.harness/tests/test_project_entrypoints_schema.py`
- Test: `.harness/tests/test_project_init_skill.py`
- Test: `installer/tests/test_asset_manifest.py`
- Test: `installer/tests/test_installer_engine.py`

Depends on: []

Acceptance:
- Managed block version changes from `harness-entrypoint-block-v1` to `harness-entrypoint-block-v2` across the template, script constant, schema, template contract, tests, and installer payload.
- Running `init-project-entrypoint.py --write` replaces an existing v1 managed block with the full v2 block while preserving user prose outside the markers.
- The v2 block maps terminal new workflow start to `start-workflow.py`, backlog intake to `backlog-intake.py`, and backlog consumption to `backlog-consume.py`.
- Entry point updates do not re-run or overwrite `.harness/contracts/project-contracts.json`.
- Installer payload fixed assets match the source `.harness` assets.

Verification:
- Run: `python3 .harness/tests/test_init_project_entrypoint.py`
- Run: `python3 .harness/tests/test_project_entrypoints_schema.py`
- Run: `python3 .harness/tests/test_project_init_skill.py`
- Run: `python3 installer/tests/test_asset_manifest.py`
- Run: `python3 installer/tests/test_installer_engine.py`
- Check: `cmp -s .harness/templates/entrypoint-managed-block.template.md src/harness_engineering_installer/payload/.harness/templates/entrypoint-managed-block.template.md`.

<a id="task-002-bump-package-release-version"></a>

### TASK-002: Bump package release version

Goal: Bump the installer package version for the managed block v2 fixed assets and pass the local package release gates.

Files:
- Modify: `pyproject.toml`
- Modify: `src/harness_engineering_installer/__init__.py`
- Test: `installer/tests/`
- Test: `installer/release/check_artifacts.py`
- Test: `installer/release/smoke_install.py`

Depends on: [TASK-001]

Acceptance:
- `pyproject.toml` and `src/harness_engineering_installer/__init__.py` declare the same next patch version.
- Local installer tests pass against the bumped version.
- Built distribution artifacts pass `installer/release/check_artifacts.py`.
- Installed wheel smoke testing passes through `installer/release/smoke_install.py`.
- No generated `dist/` artifacts are committed.

Verification:
- Run: `python3 -m unittest discover -s installer/tests -p 'test_*.py'`
- Run: `python3 -m build`
- Run: `python3 installer/release/check_artifacts.py dist`
- Run: `python3 installer/release/smoke_install.py dist`
- Check: `git status --short dist` shows no tracked release artifacts staged.

<a id="task-003-normalize-framework-contract-prose"></a>

### TASK-003: Normalize framework contract prose

Goal: Translate and standardize static Harness framework documentation, rules, skills, templates, and schema prose to English.

Files:
- Modify: `.harness/ARCHITECTURE.md`
- Modify: `.harness/rules/`
- Modify: `.harness/skills/`
- Modify: `.harness/templates/`
- Modify: `.harness/schemas/`
- Test: `.harness/tests/test_plan_writing_templates.py`
- Test: `.harness/tests/test_tasks_schema.py`
- Test: `.harness/tests/test_workflow_state_schema.py`

Depends on: [TASK-001, TASK-002]

Acceptance:
- Static `.harness` framework prose is English across architecture, rules, skills, templates, and schemas.
- Schema descriptions, `$comment` values, template text, and skill instructions preserve their existing Harness semantics.
- No task, testing, review, backlog, handoff, commit, or archive lifecycle boundary is weakened or moved out of its established layer.

Verification:
- Run: `python3 .harness/tests/test_plan_writing_templates.py`
- Run: `python3 .harness/tests/test_tasks_schema.py`
- Run: `python3 .harness/tests/test_workflow_state_schema.py`
- Check: `rg -n "\p{Han}" .harness/ARCHITECTURE.md .harness/rules .harness/skills .harness/templates .harness/schemas` reports no remaining human-facing Chinese prose.

<a id="task-004-normalize-script-diagnostics"></a>

### TASK-004: Normalize script diagnostics

Goal: Translate and standardize `.harness/scripts` comments, docstrings, CLI help, errors, warnings, and emitted user-facing messages to English.

Files:
- Modify: `.harness/scripts/`
- Modify: `.harness/tests/`
- Test: `.harness/tests/test_validate_state.py`
- Test: `.harness/tests/test_lint_harness.py`
- Test: `.harness/tests/test_state_write.py`
- Test: `.harness/tests/test_harness_cli.py`

Depends on: [TASK-001, TASK-002, TASK-003]

Acceptance:
- Script comments and docstrings are English.
- CLI help, warnings, errors, success messages, and JSON-facing diagnostic strings are English.
- Existing script gateway responsibilities and side effects are unchanged.
- Tests that assert exact diagnostics are updated to the new English wording without relaxing the behavioral assertions.

Verification:
- Run: `python3 .harness/tests/test_validate_state.py`
- Run: `python3 .harness/tests/test_lint_harness.py`
- Run: `python3 .harness/tests/test_state_write.py`
- Run: `python3 .harness/tests/test_harness_cli.py`
- Check: `rg -n "\p{Han}" .harness/scripts` reports no remaining human-facing Chinese script text.

<a id="task-005-add-language-regression-guard"></a>

### TASK-005: Add language regression guard

Goal: Add a regression test and final validation pass that keeps `.harness` human-facing assets standardized in English.

Files:
- Create: `.harness/tests/test_language_standardization.py`
- Modify: `.harness/tests/`
- Test: `.harness/tests/test_language_standardization.py`
- Test: `.harness/tests/test_materialize_tasks.py`
- Test: `.harness/tests/test_lifecycle_transaction.py`
- Test: `.harness/tests/test_backlog_consume.py`

Depends on: [TASK-001, TASK-002, TASK-003, TASK-004]

Acceptance:
- A dedicated language-standardization test fails on accidental Chinese human-facing text under `.harness`.
- Existing Harness regression tests pass with English diagnostics and expectations.
- `rg -n "\p{Han}" .harness` has no unexplained matches after the plan completes.

Verification:
- Run: `python3 .harness/tests/test_language_standardization.py`
- Run: `python3 .harness/tests/test_materialize_tasks.py`
- Run: `python3 .harness/tests/test_lifecycle_transaction.py`
- Run: `python3 .harness/tests/test_backlog_consume.py`
- Run: `python3 .harness/tests/test_lint_harness.py`
- Check: `rg -n "\p{Han}" .harness` reports no remaining unexplained matches.
