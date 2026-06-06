# backlog-rules.md

Backlog intake records newly arriving work while the current workflow remains active. It belongs to the intake-side subsystem, not the execution scheduler. `backlogs.json` stores only pending items that have not yet been taken over by a workflow or plan; consumed items must be removed through the consumption gateway and recorded in the consumption audit log.

## 1. Truth Sources

- Pending queue contract: `.harness/schemas/backlogs.schema.json`
- Consumption event contract: `.harness/schemas/backlog-consumption-event.schema.json`
- Initial template: `.harness/templates/backlogs.template.json`
- Pending queue: `work/backlog/backlogs.json`
- Consumption audit log: `work/backlog/consumed.jsonl`
- Append gateway: `.harness/scripts/backlog-intake.py`
- Consumption gateway: `.harness/scripts/backlog-consume.py`

`.harness/` stores only schemas, templates, rules, scripts, and tests. Backlog runtime data belongs only under `work/backlog/`.

## 2. Dispatch Semantics

`dispatch` is a request signal, not an execution instruction:

- `queue`: record as ordinary follow-up work to evaluate after the current active workflow completes.
- `preempt`: request an LLM evaluation of whether the current active workflow should be interrupted.

Neither mode may modify `workflow-state.json`, `tasks.json`, active plan files, or `handoff.md`. `preempt` does not automatically activate work; it only raises the priority of semantic evaluation.

## 3. Gateway Boundary

`backlog-intake.py` is the only deterministic append gateway for `work/backlog/backlogs.json`.

The script must:

- Create `work/backlog/backlogs.json` from `.harness/templates/backlogs.template.json` when the store is missing.
- Allocate the next `BL-NNN` from `nextId` and increment `nextId`.
- Deterministically migrate old stores that lack `nextId`: `nextId = max(existing BL-NNN) + 1`.
- Validate the existing store before appending and validate the full new store before writing.
- Atomically write only `work/backlog/backlogs.json`.

`backlog-consume.py` is the only deterministic consumption gateway for pending items.

The script must:

- Validate the existing `backlogs.json`.
- Validate that the target item exists.
- Validate that `targetRef` is either `plan:<PLAN-ID>` or `workflow:<workflowId>`.
- For `plan:<PLAN-ID>`, confirm that the active plan package has `plan.md`, `tasks.json`, and `handoff.md`, that `Plan Review Gate` is passed, that `tasks.json` is valid, and that the plan or handoff references the backlog id or `sourceRef`.
- For `workflow:<workflowId>`, confirm that `workflow-state.json` validates, the workflowId matches, active refs are empty, and session audit evidence references the backlog id or `sourceRef`.
- Write a schema-valid `work/backlog/consumed.jsonl` event that preserves the complete original item.
- Delete the consumed item from `backlogs.json.items` while preserving `nextId`.
- If the consumed event has been written but the `backlogs.json` write-back fails, roll back the just-written consumed event; the same item must never remain in both the pending queue and the consumed audit.

Neither backlog script may:

- Modify `work/workflow-state.json`.
- Modify any `work/plans/active/<PLAN-ID>/tasks.json`.
- Create, activate, pause, or archive a plan.
- Modify active plan files or `handoff.md`.
- Model testing or review as a backlog task.

## 4. LLM Boundary

Whether a `preempt` item affects the current workflow is an LLM semantic judgment. That judgment must still follow the normal Harness lifecycle rules and write gateways. The intake script only records auditable input.
