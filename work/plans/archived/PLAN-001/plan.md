# PLAN-001: Backlog Intake Contract

## Background and Goal

Backlog intake is still described only as a design sketch under `harness-design/backlogs.schema.md` and `harness-design/backlogs.template.json`. The Harness lifecycle now has deterministic gates for session start, task execution, review, completion, and archive, but new incoming work still has no schema-backed intake path.

The goal is to make backlog intake a first-class Harness subsystem: a schema-valid backlog store under `work/backlog/backlogs.json`, a deterministic append gateway, CLI access, rules, and regression tests.

## Scope

- Move backlog item shape into `.harness/schemas/backlogs.schema.json`.
- Provide `.harness/templates/backlogs.template.json` as the schema-valid initial backlog store.
- Add a deterministic backlog intake script that appends new backlog items without mutating workflow state.
- Wire the unified `.harness/scripts/harness` CLI to the intake script.
- Document intake semantics, especially `queue` vs `preempt`.
- Update architecture/session-start expectations so backlog intake is part of the Harness contract.

## Non-Scope

- Do not implement backlog prioritization or scheduling.
- Do not turn a backlog item into an active plan automatically.
- Do not interrupt or mutate the current active workflow from intake.
- Do not create testing or review tasks.
- Do not move backlog runtime data into `.harness/`.

## Implementation Direction

Keep `.harness/` as the contract/tooling layer and `work/backlog/backlogs.json` as runtime data. The intake script should be the single deterministic gateway for appending backlog items. The LLM remains responsible for deciding whether a `preempt` item should interrupt the current workflow; the script only records the item and validates the store.

## File Boundaries

- Create: `.harness/schemas/backlogs.schema.json`
- Create: `.harness/templates/backlogs.template.json`
- Create: `.harness/rules/backlog-rules.md`
- Create: `.harness/scripts/backlog-intake.py`
- Create: `.harness/tests/test_backlogs_schema.py`
- Create: `.harness/tests/test_backlog_intake.py`
- Modify: `.harness/scripts/harness`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/tests/test_harness_cli.py`
- Modify: `.harness/tests/test_session_start.py`
- Modify: `harness-design/architecture.md`
- Modify: `harness-design/backlogs.schema.md`
- Modify: `learning-notes/README.md`

## Task Decomposition

The plan is split by contract boundary. First define and validate the backlog data contract. Then implement the write gateway. Finally wire rules, CLI, and session asset checks.

## Verification Strategy

Run focused schema, intake, CLI, and session-start tests after each related task. Run full Harness unittest and lint after the plan is complete.

## Risks and Open Questions

- Risk: `preempt` may be mistaken for immediate execution. The rule document and script output must state that `preempt` only requests LLM evaluation.
- Risk: duplicate IDs or ad hoc JSON edits can corrupt intake history. The script must allocate IDs deterministically and validate the full store before writing.
- Open questions: None for the initial intake contract.

## Task Contracts

<a id="task-001-define-backlog-schema"></a>

### TASK-001: Define backlog schema

Goal: Define the machine-checkable backlog store contract and a valid initial template.

Files:
- Create: `.harness/schemas/backlogs.schema.json`
- Create: `.harness/templates/backlogs.template.json`
- Modify: `harness-design/architecture.md`
- Modify: `harness-design/backlogs.schema.md`
- Test: `.harness/tests/test_backlogs_schema.py`

Depends on: []

Acceptance:
- `.harness/schemas/backlogs.schema.json` validates `.harness/templates/backlogs.template.json`.
- Backlog item IDs use `BL-001` style identifiers and are unique.
- `dispatch` is limited to `queue` or `preempt`.
- `sourceRef` and `createdAt` are required for auditability.
- Runtime backlog data remains under `work/backlog/backlogs.json`, not `.harness/`.

Verification:
- Run: `python3 .harness/tests/test_backlogs_schema.py`
- Check: architecture and design docs describe `.harness/schemas/backlogs.schema.json`, `.harness/templates/backlogs.template.json`, and `work/backlog/backlogs.json` consistently.

<a id="task-002-implement-backlog-intake-gateway"></a>

### TASK-002: Implement backlog intake gateway

Goal: Add a deterministic script that appends schema-valid backlog items through one gateway.

Files:
- Create: `.harness/scripts/backlog-intake.py`
- Test: `.harness/tests/test_backlog_intake.py`

Depends on: [TASK-001]

Acceptance:
- The script creates `work/backlog/backlogs.json` from the template when the store is missing.
- The script appends a new item with the next available `BL-NNN` ID.
- The script accepts `title`, `summary`, `dispatch`, `sourceRef`, optional `notes`, and optional `createdAt`.
- The script validates the full backlog store before atomic write.
- The script never writes `workflow-state.json`, `tasks.json`, or active plan files.

Verification:
- Run: `python3 .harness/tests/test_backlog_intake.py`
- Check: repeated intake calls produce sequential IDs and preserve existing items.

<a id="task-003-wire-backlog-intake-rules-and-cli"></a>

### TASK-003: Wire backlog intake rules and CLI

Goal: Expose backlog intake through the Harness CLI and document the lifecycle boundary.

Files:
- Create: `.harness/rules/backlog-rules.md`
- Modify: `.harness/scripts/harness`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/tests/test_harness_cli.py`
- Modify: `.harness/tests/test_session_start.py`
- Modify: `harness-design/architecture.md`
- Modify: `learning-notes/README.md`

Depends on: [TASK-001, TASK-002]

Acceptance:
- `.harness/scripts/harness backlog-intake ...` delegates to `.harness/scripts/backlog-intake.py`.
- `session-start.py` includes backlog schema, template, rule, and script in required Harness assets.
- `backlog-rules.md` states that `queue` records normal follow-up work and `preempt` requests evaluation, but neither mutates the active workflow.
- Documentation identifies backlog intake as intake-side runtime data, separate from active plan execution.

Verification:
- Run: `python3 .harness/tests/test_harness_cli.py`
- Run: `python3 .harness/tests/test_session_start.py`
- Check: `python3 .harness/scripts/harness --help` lists the backlog intake subcommand.
