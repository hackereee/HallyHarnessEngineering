# PLAN-001: Define Harness Task Contract

## Background and Goal

Define the Harness task contract so an L2/L3 plan can be materialized into a schema-valid `tasks.json` and resumed by another Agent without relying on conversation history.

## Scope

- Define the machine-checkable task structure.
- Provide a template task manifest.
- Document the lifecycle rule that `tasks.json` is the task-level execution truth source.

## Non-Scope

- Do not activate the first task from plan writing.
- Do not write `workflow-state.json` directly.
- Do not model testing or review as separate tasks.

## Implementation Direction

Keep `plan.md` as the planning truth source, record a passed planning-time review gate, and use structured task contract sections for deterministic extraction. Let `.harness/scripts/materialize-tasks.py` generate `tasks.json`; let workflow lifecycle tooling handle task activation and state transitions.

## File Boundaries

- Create: `.harness/schemas/tasks.schema.json`
- Create: `.harness/templates/tasks.template.json`
- Modify: `.harness/rules/workflow-lifecycle.md`
- Test: `.harness/tests/test_tasks_schema.py`
- Test: `.harness/tests/test_materialize_tasks.py`

## Task Decomposition

The plan is split by contract boundary: schema/template first, parser/materialization second, lifecycle documentation third. Each task has explicit file boundaries, acceptance, and verification evidence.

## Verification Strategy

Run the task schema and materialization tests after any change to the task contract, parser, or template. Run workflow-state validation tests after lifecycle wording or state shape changes.

## Risks and Open Questions

- Risk: A future change may revise the `review` rubric or threshold; update schema, template, lifecycle rules, scripts, tests, and this plan template together.
- Open questions: None for the initial contract.

## Plan Review Gate

Status: passed
Reviewer: harness-reviewer
Reviewed At: 2026-04-27T00:00:00+08:00

Checks:
- Scope, non-scope, file boundaries, dependencies, acceptance, and verification are reviewable.
- Task contracts are parseable and contain no testing-only or review-only tasks.
- Lifecycle boundaries are preserved: plan writing stops before task activation.

Findings:
- No blocking findings.

## Task Contracts

<a id="task-001-define-tasks-schema"></a>

### TASK-001: Define tasks schema

Goal: Define the machine-checkable schema for plan tasks.

Files:
- Create: `.harness/schemas/tasks.schema.json`
- Create: `.harness/templates/tasks.template.json`
- Test: `.harness/tests/test_tasks_schema.py`

Depends on: []

Acceptance:
- `tasks.schema.json` validates `tasks.template.json`.
- Task IDs use `TASK-001` style identifiers.
- `planSection` points to a stable anchor in `plan.md`.
- `review` is initialized as a schema-supported gate summary.

Verification:
- Run: `python3 .harness/tests/test_tasks_schema.py`
- Check: `tasks.template.json` uses `taskId`, `planSection`, `dependsOn`, `acceptance`, `verification`, and `review`.

<a id="task-002-materialize-task-contracts"></a>

### TASK-002: Materialize task contracts

Goal: Generate schema-valid `tasks.json` from structured task contract sections in `plan.md`.

Files:
- Modify: `.harness/scripts/materialize-tasks.py`
- Test: `.harness/tests/test_materialize_tasks.py`

Depends on: [TASK-001]

Acceptance:
- The script extracts only structured task contracts with stable anchors.
- The script rejects unknown dependencies and missing verification.
- Generated tasks are initially `idle`, owned by `developer`, and have `review.lastResult = "not_run"`.

Verification:
- Run: `python3 .harness/tests/test_materialize_tasks.py`
- Check: generated `tasks.json` contains the default `review` gate summary.

<a id="task-003-document-lifecycle-boundary"></a>

### TASK-003: Document lifecycle boundary

Goal: Document where plan writing stops and workflow lifecycle task activation begins.

Files:
- Modify: `.harness/rules/workflow-lifecycle.md`
- Test: `.harness/tests/test_validate_state.py`

Depends on: [TASK-001, TASK-002]

Acceptance:
- The rule states that planning keeps `activeTaskId = null`.
- The rule states that task activation sets `activeTaskId` and moves the task to `implementing/developer`.
- Testing and review remain workflow gates, not independent tasks.

Verification:
- Run: `python3 .harness/tests/test_validate_state.py`
- Check: workflow-state validation accepts planning state with `activeTaskId = null` and `ownerRole = planner`.
