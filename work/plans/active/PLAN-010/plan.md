# PLAN-010: Backlog Consumption Queue

## Background and Goal

`work/backlog/backlogs.json` currently acts as an append-only incoming work store. The approved design in `work/designs/2026-04-28-backlog-consumption-design.md` changes that role: `backlogs.json` should contain only pending items, and a consumed backlog item should be removed only after a workflow or plan has formally taken ownership of it.

The goal is to implement that design as a schema-backed, script-gated, auditable Harness subsystem:

- `backlogs.json` becomes a pending queue with `nextId`.
- `backlog-intake.py` allocates IDs from `nextId`, so consumed items never cause ID reuse.
- `backlog-consume.py` removes items only after downstream ownership evidence exists.
- `consumed.jsonl` preserves a schema-valid audit event for every removed item.

## Scope

- Add `nextId` to the backlog store schema, template, intake script, tests, and current runtime store.
- Add a backlog consumption event schema.
- Add a deterministic backlog consumption script.
- Wire the new command through the unified Harness CLI.
- Update `session-start.py` required assets so the consumption contract is part of Harness core assets.
- Update Harness architecture, backlog rules, backlog design notes, and learning notes to describe pending queue plus consumed audit log.

## Non-Scope

- Do not implement backlog prioritization or scheduling.
- Do not automatically create, activate, complete, or archive workflows from backlog items.
- Do not store consumed status inside `backlogs.json`.
- Do not let backlog scripts write `workflow-state.json`, `tasks.json`, active plan files, or `handoff.md`.
- Do not model testing, review, architecture impact, commit, or handoff as tasks.

## Implementation Direction

Keep backlog consumption as an intake-side operation, not a lifecycle transition. `backlog-intake.py` and `backlog-consume.py` may write only `work/backlog/` files. The consume script can read workflow, plan, tasks, handoff, and session files to prove downstream ownership, but it must not mutate them.

Use schema and tests for every deterministic rule:

- `nextId` is required in `backlogs.json`.
- consumption events are schema-valid JSONL records.
- plan targets require a complete active plan package, passed Plan Review Gate, valid `tasks.json`, and a downstream backlog reference.
- workflow targets require matching validated workflow state and a session audit source reference.

## File Boundaries

- Modify: `.harness/schemas/backlogs.schema.json`
- Create: `.harness/schemas/backlog-consumption-event.schema.json`
- Modify: `.harness/templates/backlogs.template.json`
- Modify: `.harness/scripts/backlog-intake.py`
- Create: `.harness/scripts/backlog-consume.py`
- Modify: `.harness/scripts/harness`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/ARCHITECTURE.md`
- Modify: `.harness/rules/backlog-rules.md`
- Modify: `harness-design/backlogs.schema.md`
- Modify: `learning-notes/README.md`
- Modify: `work/backlog/backlogs.json`
- Test: `.harness/tests/test_backlogs_schema.py`
- Test: `.harness/tests/test_backlog_intake.py`
- Create: `.harness/tests/test_backlog_consume.py`
- Modify: `.harness/tests/test_harness_cli.py`
- Modify: `.harness/tests/test_session_start.py`

## Task Decomposition

The implementation is split by contract boundary:

- `TASK-001` changes the pending queue contract and intake ID allocation.
- `TASK-002` adds the consumption event contract and deterministic consume gateway.
- `TASK-003` wires the gateway into CLI, session-start required assets, and documentation.

Testing, review, architecture impact, lifecycle activation, task commit, and archive are workflow gates or audit actions, not standalone tasks.

## Verification Strategy

Run focused tests after each task. Run the full Harness unittest suite and lint/state validation before completion, because this work changes core schema, scripts, docs, CLI, and required startup assets.

## Architecture Impact

- Expected target project architecture impact: none. This changes Harness framework behavior only; target project root `ARCHITECTURE.md` should remain business architecture.
- Expected Harness framework architecture impact: yes. `.harness/ARCHITECTURE.md`, `.harness/rules/backlog-rules.md`, and backlog design notes must document `backlogs.json` as pending queue and `consumed.jsonl` as audit log.
- This is an Architecture Impact gate record, not a standalone task.

## Risks and Open Questions

- Risk: deleting a backlog item before downstream artifacts reference its source would lose traceability. The consume script must block this.
- Risk: keeping `nextId` optional would allow ID reuse after the queue is empty. The schema must require it.
- Risk: unvalidated JSONL events would become another weak audit surface. The event schema and consume tests must validate event shape.
- Open questions: none. The user approved the consumption timing and design on 2026-04-28.

## Plan Review Gate

Status: passed
Reviewer: user-approved-design-review
Reviewed At: 2026-04-28T12:30:00+08:00

Checks:
- Scope and non-scope match `work/designs/2026-04-28-backlog-consumption-design.md`.
- Task contracts are parseable and contain no testing-only or review-only tasks.
- File boundaries cover schema, template, scripts, CLI, session-start assets, docs, runtime migration, and tests.
- Acceptance criteria are observable through schema validation, focused tests, lint, and state validation.
- Architecture Impact is recorded as a gate, not a standalone task.

Findings:
- No blocking findings.

## Task Contracts

<a id="task-001-pending-queue-contract"></a>

### TASK-001: Pending queue contract and intake IDs

Goal: Add `nextId` to the backlog pending queue and make intake allocate IDs from that cursor instead of remaining items.

Files:
- Modify: `.harness/schemas/backlogs.schema.json`
- Modify: `.harness/templates/backlogs.template.json`
- Modify: `.harness/scripts/backlog-intake.py`
- Modify: `work/backlog/backlogs.json`
- Test: `.harness/tests/test_backlogs_schema.py`
- Test: `.harness/tests/test_backlog_intake.py`

Depends on: []

Acceptance:
- `backlogs.schema.json` requires integer `nextId`.
- `backlogs.template.json` contains `nextId: 1`.
- Existing stores without `nextId` migrate deterministically to `max(BL-NNN) + 1`.
- Intake allocates `BL-NNN` from `nextId`, increments `nextId`, and does not reuse IDs after items are removed.
- The current runtime store records `nextId: 7` while preserving existing pending items.

Verification:
- Run: `python3 .harness/tests/test_backlogs_schema.py`
- Run: `python3 .harness/tests/test_backlog_intake.py`
- Check: `python3 -m json.tool work/backlog/backlogs.json`

<a id="task-002-consumption-gateway"></a>

### TASK-002: Consumption event schema and gateway

Goal: Add the schema-backed `backlog-consume.py` gateway that removes a pending item only after downstream plan or workflow ownership evidence exists.

Files:
- Create: `.harness/schemas/backlog-consumption-event.schema.json`
- Create: `.harness/scripts/backlog-consume.py`
- Test: `.harness/tests/test_backlog_consume.py`

Depends on: [TASK-001]

Acceptance:
- `backlog-consume.py` validates the pending store before mutation.
- The script rejects unknown backlog IDs and malformed `targetRef` values.
- `plan:<PLAN-ID>` targets require `plan.md`, `tasks.json`, `handoff.md`, passed Plan Review Gate, valid `tasks.json`, and a downstream backlog id or `sourceRef` reference.
- `workflow:<workflowId>` targets require matching validated workflow state and a session audit source reference.
- Successful consumption appends one schema-valid event to `work/backlog/consumed.jsonl`.
- Successful consumption removes only the consumed item from `backlogs.json` and preserves `nextId`.
- The script writes only `work/backlog/backlogs.json` and `work/backlog/consumed.jsonl`.

Verification:
- Run: `python3 .harness/tests/test_backlog_consume.py`
- Run: `python3 .harness/tests/test_backlog_intake.py`
- Check: `rg -n "workflow-state|tasks.json|consumed.jsonl" .harness/scripts/backlog-consume.py .harness/tests/test_backlog_consume.py`

<a id="task-003-cli-session-docs"></a>

### TASK-003: CLI, session assets, and documentation

Goal: Expose backlog consumption through the Harness CLI and document pending queue plus consumed audit semantics across Harness docs.

Files:
- Modify: `.harness/scripts/harness`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/ARCHITECTURE.md`
- Modify: `.harness/rules/backlog-rules.md`
- Modify: `harness-design/backlogs.schema.md`
- Modify: `learning-notes/README.md`
- Test: `.harness/tests/test_harness_cli.py`
- Test: `.harness/tests/test_session_start.py`

Depends on: [TASK-001, TASK-002]

Acceptance:
- `.harness/scripts/harness --help` lists `backlog-consume`.
- `.harness/scripts/harness backlog-consume ...` delegates to `.harness/scripts/backlog-consume.py`.
- `session-start.py` requires `.harness/scripts/backlog-consume.py` and `.harness/schemas/backlog-consumption-event.schema.json`.
- Docs state that `backlogs.json` contains only pending items.
- Docs state that `consumed.jsonl` is the audit log for removed items.
- Docs preserve the boundary that backlog scripts do not mutate workflow or task execution state.

Verification:
- Run: `python3 .harness/tests/test_harness_cli.py`
- Run: `python3 .harness/tests/test_session_start.py`
- Run: `python3 .harness/scripts/lint-harness.py --root .`
- Run: `python3 .harness/scripts/validate-state.py --state work/workflow-state.json --schema .harness/schemas/workflow-state.schema.json`
