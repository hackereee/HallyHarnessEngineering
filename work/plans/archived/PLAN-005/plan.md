# PLAN-005: Close Harness Architecture Review Gaps

## Background and Goal

The architecture review found several places where the documented Harness lifecycle is stronger than the implemented schema and script gates. This plan closes those gaps so invalid workflow states cannot pass as merely "unusual but schema-valid" runtime data.

## Scope

- Define or remove the currently underspecified paused workflow behavior.
- Prevent terminal workflows from being reopened through partial `workflowStatus` patches.
- Require active plan references for active planning and archiving phases.
- Clarify the project contracts directory as an initialized but optionally unconfigured contract location.
- Extend source linting so direct workflow-state writes are not limited to Python files.
- Add regression tests before production changes.

## Non-Scope

- Do not introduce a new backlog or priority system.
- Do not change archived plan history.
- Do not make project environment checks part of `session-start.py`.
- Do not model testing or review as standalone tasks.

## Implementation Direction

Keep lifecycle truth in `workflow-state.json` and `tasks.json`, but strengthen deterministic gates where the current state machine is underconstrained. Favor schema constraints when shape rules are expressible, script checks when transition history matters, and rule documentation only for semantics that cannot be represented mechanically.

## File Boundaries

- Modify: `.harness/schemas/workflow-state.schema.json`
- Modify: `.harness/scripts/state-write.py`
- Modify: `.harness/scripts/lifecycle-transaction.py`
- Modify: `.harness/scripts/lint-harness.py`
- Modify: `.harness/scripts/harness`
- Modify: `.harness/rules/workflow-lifecycle.md`
- Modify: `.harness/rules/archive-rules.md`
- Modify: `harness-design/architecture.md`
- Modify: `.harness/skills/project-init/SKILL.md`
- Create: `.harness/contracts/.gitkeep`
- Test: `.harness/tests/test_workflow_state_schema.py`
- Test: `.harness/tests/test_validate_state.py`
- Test: `.harness/tests/test_state_write.py`
- Test: `.harness/tests/test_lifecycle_transaction.py`
- Test: `.harness/tests/test_lint_harness.py`
- Test: `.harness/tests/test_harness_cli.py`
- Test: `.harness/tests/test_project_init_skill.py`

## Task Decomposition

This plan uses one delivery task because the requested changes are one lifecycle-hardening unit: the schema, gateways, rules, and tests must move together to avoid creating an inconsistent intermediate contract.

## Verification Strategy

Use focused red/green checks for each changed behavior, then run the whole Harness test suite, `lint-harness.py`, and `validate-state.py`. The task cannot enter `done` until verification and structured review gates both pass.

## Risks and Open Questions

- Risk: Removing `paused` may be incompatible with a future pause/resume feature. That feature should be introduced later with explicit lifecycle rules and script gates.
- Risk: Broader source scanning can produce false positives if scripts mention `workflow-state.json` in documentation strings. Tests should pin only actual write patterns.
- Open questions: None blocking. The requested direction is to apply all review recommendations.

## Plan Review Gate

Status: passed
Reviewer: harness-reviewer
Reviewed At: 2026-04-27T21:00:00+08:00

Checks:
- Scope, non-scope, file boundaries, dependencies, acceptance, and verification are reviewable.
- The plan contains one delivery task and no testing-only or review-only tasks.
- Lifecycle boundaries are preserved: plan writing stops before task activation.
- All recommended architecture review findings map to acceptance criteria.

Findings:
- No blocking findings.

## Task Contracts

<a id="task-001-harden-lifecycle-contracts"></a>

### TASK-001: Harden lifecycle contracts

Goal: Align architecture, schema, scripts, and tests around the lifecycle review recommendations.

Files:
- Create: `.harness/contracts/.gitkeep`
- Modify: `.harness/schemas/workflow-state.schema.json`
- Modify: `.harness/scripts/state-write.py`
- Modify: `.harness/scripts/lifecycle-transaction.py`
- Modify: `.harness/scripts/lint-harness.py`
- Modify: `.harness/scripts/harness`
- Modify: `.harness/rules/workflow-lifecycle.md`
- Modify: `.harness/rules/archive-rules.md`
- Modify: `harness-design/architecture.md`
- Modify: `.harness/skills/project-init/SKILL.md`
- Test: `.harness/tests/test_workflow_state_schema.py`
- Test: `.harness/tests/test_validate_state.py`
- Test: `.harness/tests/test_state_write.py`
- Test: `.harness/tests/test_lifecycle_transaction.py`
- Test: `.harness/tests/test_lint_harness.py`
- Test: `.harness/tests/test_harness_cli.py`
- Test: `.harness/tests/test_project_init_skill.py`

Depends on: []

Acceptance:
- `workflowStatus` no longer exposes an undefined paused runtime shape.
- Reopening a terminal workflow is only possible through explicit terminal reset with a new `workflowId`.
- Active `planning` and `archiving` states require an active plan reference and package.
- Lifecycle transactions reject non-active workflow statuses before changing task or workflow state.
- `lint-harness.py` scans Python and extensionless production scripts for direct `workflow-state.json` writes.
- Architecture and project-init docs state that `.harness/contracts/` is present while `project-contracts.json` is created by project initialization and may be not configured.

Verification:
- Run: `python3 .harness/tests/test_workflow_state_schema.py`
- Run: `python3 .harness/tests/test_validate_state.py`
- Run: `python3 .harness/tests/test_state_write.py`
- Run: `python3 .harness/tests/test_lifecycle_transaction.py`
- Run: `python3 .harness/tests/test_lint_harness.py`
- Run: `python3 .harness/tests/test_harness_cli.py`
- Run: `python3 .harness/tests/test_project_init_skill.py`
- Run: `python3 -m unittest discover -s .harness/tests -p 'test_*.py'`
- Run: `python3 .harness/scripts/lint-harness.py --root .`
- Run: `python3 .harness/scripts/validate-state.py --state work/workflow-state.json --schema .harness/schemas/workflow-state.schema.json`
