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

Keep `plan.md` as the planning truth source and use structured task contract sections for deterministic extraction. Let `.harness/scripts/materialize-tasks.py` generate `tasks.json`; let workflow lifecycle tooling handle task activation and state transitions.

## File Boundaries

- Create: `.harness/schemas/tasks.schema.json`
- Create: `.harness/templates/tasks.template.json`
- Modify: `.harness/rules/workflow-lifecycle.md`
- Test: `.harness/scripts/test_tasks_schema.py`
- Test: `.harness/scripts/test_materialize_tasks.py`

## Task Decomposition

The plan is split by contract boundary: schema/template first, parser/materialization second, lifecycle documentation third. Each task has explicit file boundaries, acceptance, and verification evidence.

## Verification Strategy

Run the task schema and materialization tests after any change to the task contract, parser, or template. Run workflow-state validation tests after lifecycle wording or state shape changes.

## Risks and Open Questions

- Risk: A future change may add a `review` block to `tasks.json`; update schema, template, lifecycle rules, scripts, tests, and this plan template together.
- Open questions: None for the initial contract.

## Task Contracts

<a id="task-001-define-tasks-schema"></a>

### TASK-001: Define tasks schema

Goal: Define the machine-checkable schema for plan tasks.

Files:
- Create: `.harness/schemas/tasks.schema.json`
- Create: `.harness/templates/tasks.template.json`
- Test: `.harness/scripts/test_tasks_schema.py`

Depends on: []

Acceptance:
- `tasks.schema.json` validates `tasks.template.json`.
- Task IDs use `TASK-001` style identifiers.
- `planSection` points to a stable anchor in `plan.md`.

Verification:
- Run: `python3 .harness/scripts/test_tasks_schema.py`
- Check: `tasks.template.json` uses `taskId`, `planSection`, `dependsOn`, `acceptance`, and `verification`.

<a id="task-002-materialize-task-contracts"></a>

### TASK-002: Materialize task contracts

Goal: Generate schema-valid `tasks.json` from structured task contract sections in `plan.md`.

Files:
- Modify: `.harness/scripts/materialize-tasks.py`
- Test: `.harness/scripts/test_materialize_tasks.py`

Depends on: [TASK-001]

Acceptance:
- The script extracts only structured task contracts with stable anchors.
- The script rejects unknown dependencies and missing verification.
- Generated tasks are initially `idle` and owned by `developer`.

Verification:
- Run: `python3 .harness/scripts/test_materialize_tasks.py`
- Check: generated `tasks.json` does not contain a `review` field before schema support exists.

<a id="task-003-document-lifecycle-boundary"></a>

### TASK-003: Document lifecycle boundary

Goal: Document where plan writing stops and workflow lifecycle task activation begins.

Files:
- Modify: `.harness/rules/workflow-lifecycle.md`
- Test: `.harness/scripts/test_validate_state.py`

Depends on: [TASK-001, TASK-002]

Acceptance:
- The rule states that planning keeps `activeTaskId = null`.
- The rule states that task activation sets `activeTaskId` and moves the task to `implementing/developer`.
- Testing and review remain workflow gates, not independent tasks.

Verification:
- Run: `python3 .harness/scripts/test_validate_state.py`
- Check: workflow-state validation accepts planning state with `activeTaskId = null` and `ownerRole = planner`.
