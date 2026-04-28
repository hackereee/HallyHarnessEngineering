# Backlog Consumption Design

Date: 2026-04-28
Status: approved-for-spec

## Decision

`work/backlog/backlogs.json` will become a pending intake queue. A backlog item is removed from `items` only after downstream Harness artifacts have formally taken ownership of it.

This design rejects deleting an item when an Agent merely reads or selects it. Consumption must happen through a deterministic script after the receiving workflow or plan has enough evidence to survive session interruption.

## Goals

- Keep `backlogs.json` clean: it contains only unconsumed pending work.
- Preserve auditability after deletion.
- Prevent `BL-NNN` id reuse after items are consumed.
- Keep backlog consumption outside workflow execution state: no direct writes to `workflow-state.json`, `tasks.json`, active plan files, or `handoff.md`.
- Make the behavior testable through schema and script regression tests.

## Non-Goals

- Do not build backlog prioritization or scheduling.
- Do not auto-create or auto-activate workflows from backlog items.
- Do not use `status=consumed` inside `backlogs.json`; consumed items leave the pending queue.
- Do not model testing or review as backlog tasks.

## Data Model

### Pending Store

`work/backlog/backlogs.json` will add a required `nextId` integer:

```json
{
  "$schema": "../../.harness/schemas/backlogs.schema.json",
  "nextId": 7,
  "items": []
}
```

`nextId` is the next numeric suffix to allocate. `backlog-intake.py` must allocate `BL-<nextId>` and then increment `nextId`. It must not derive the next id from the remaining `items` array.

For existing stores without `nextId`, the migration rule is deterministic: set `nextId` to `max(existing BL numbers) + 1`. The current repository has `BL-001` through `BL-006`, so its migrated value is `7`.

### Consumption Audit

Consumed items are appended to:

```text
work/backlog/consumed.jsonl
```

Each line is one JSON object:

```json
{
  "eventType": "backlog.consumed",
  "backlogId": "BL-006",
  "consumedAt": "2026-04-28T12:00:00+08:00",
  "targetRef": "plan:PLAN-010",
  "reason": "Converted into active plan package after Plan Review Gate passed.",
  "item": {
    "id": "BL-006",
    "title": "entrypoint managed block 增加唯一性校验",
    "summary": "...",
    "dispatch": "queue",
    "sourceRef": "chat:harness-review-20260428",
    "createdAt": "2026-04-28T10:05:00+08:00"
  }
}
```

The event shape will be schema-backed by a new `.harness/schemas/backlog-consumption-event.schema.json`, because the structure is deterministic and testable.

## Consumption Timing

### L2/L3 Plan Consumption

For `targetRef = plan:<PLAN-ID>`, consumption is allowed only after:

- `work/plans/active/<PLAN-ID>/plan.md` exists.
- `work/plans/active/<PLAN-ID>/tasks.json` exists.
- `work/plans/active/<PLAN-ID>/handoff.md` exists.
- `plan.md` contains `## Plan Review Gate` and `Status: passed`.
- `tasks.json` is valid against `.harness/schemas/tasks.schema.json`.
- The plan or handoff text references the backlog id or `sourceRef`, so the deleted queue item remains traceable from the downstream artifact.

Consumption does not activate the first task and does not write `workflow-state.json`.

### L0/L1 Direct Workflow Consumption

For `targetRef = workflow:<workflowId>`, consumption is allowed only after:

- `work/workflow-state.json` exists and validates.
- `workflowId` in state matches the target ref.
- `activePlanRef = null` and `activeTaskId = null`.
- A session audit file under `work/sessions/YYYY-MM-DD/` records the backlog id or `sourceRef` as the direct workflow source.

Consumption does not complete the workflow and does not advance phase.

## Script Boundaries

### Updated `backlog-intake.py`

Responsibilities:

- Initialize missing store from `.harness/templates/backlogs.template.json`.
- Migrate old stores without `nextId` by deriving `max(BL-NNN) + 1`.
- Allocate id from `nextId`.
- Increment `nextId`.
- Validate the full store before atomic write.
- Write only `work/backlog/backlogs.json`.

### New `backlog-consume.py`

Responsibilities:

- Validate existing `backlogs.json`.
- Find exactly one item by `--id BL-NNN`.
- Validate `--target-ref` as `plan:<PLAN-ID>` or `workflow:<workflowId>`.
- Validate target ownership evidence according to the timing rules above.
- Append one schema-valid event to `work/backlog/consumed.jsonl`.
- Remove the item from `backlogs.json`.
- Atomically write the updated pending store.

It must not:

- Modify `workflow-state.json`.
- Modify `tasks.json`.
- Create, activate, pause, complete, or archive plans/workflows.
- Infer semantic priority or decide which backlog item should be consumed.

## CLI And Assets

The unified harness CLI will expose:

```bash
.harness/scripts/harness backlog-consume --id BL-006 --target-ref plan:PLAN-010 --reason "Converted into PLAN-010"
```

`session-start.py` required assets will include:

- `.harness/scripts/backlog-consume.py`
- `.harness/schemas/backlog-consumption-event.schema.json`

## Documentation Updates

Update:

- `.harness/ARCHITECTURE.md`
- `.harness/rules/backlog-rules.md`
- `harness-design/backlogs.schema.md`
- `learning-notes/README.md`

The docs must say `backlogs.json` is the pending queue, while `consumed.jsonl` is the audit log for removed items.

## Tests

Add or update tests for:

- Backlog schema requires `nextId`.
- Template contains `nextId: 1`.
- Intake allocates from `nextId`, increments it, and does not reuse ids after deletion.
- Existing store without `nextId` migrates to `max(existing id) + 1`.
- Consume rejects unknown backlog id.
- Consume rejects malformed `targetRef`.
- Consume rejects plan targets without `plan.md`, `tasks.json`, `handoff.md`, or passed Plan Review Gate.
- Consume rejects workflow targets without matching validated workflow state and session audit source reference.
- Consume removes the item and appends a JSONL event with the full original item.
- CLI lists and delegates `backlog-consume`.
- `session-start.py` blocks if required consumption assets are missing.
- `lint-harness.py --root .` still passes.

## Risks

- If consumption happens before downstream artifacts reference the backlog source, deletion loses traceability. The consume script must block this.
- If `nextId` is not required, id reuse can return when the pending queue is empty. The schema must require it.
- If JSONL events are not schema-validated, consumption audit can drift. The consume script and tests must validate each event shape.

## Acceptance

The implementation is acceptable when:

- `backlogs.json` contains only pending items.
- Consumed items are removed only through `backlog-consume.py`.
- Every consumed item has a durable event in `consumed.jsonl`.
- `BL-NNN` ids are never reused after consumption.
- No backlog script writes workflow or task execution state.
