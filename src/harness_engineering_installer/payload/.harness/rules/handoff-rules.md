# handoff-rules.md

`handoff.md` is the L2/L3 active plan recovery summary. It records enough semantic context for the next Agent to resume safely, but it is not a truth source.

Truth sources:

- Workflow state: `work/workflow-state.json`
- Task execution state: `work/plans/active/<PLAN-ID>/tasks.json`
- Planning contract: `work/plans/active/<PLAN-ID>/plan.md`
- Recovery summary: `work/plans/active/<PLAN-ID>/handoff.md`

`handoff.md` may summarize state, decisions, risks, and lifecycle transitions. If it conflicts with `workflow-state.json` or `tasks.json`, the JSON truth sources win and the handoff must be corrected.

## Required Header Fields

The top metadata block must contain these line-oriented fields:

- `workflowId`
- `planRef`
- `activeTaskId`
- `currentPhase`
- `taskStatus`
- `ownerRole`
- `sourceSessionId`

Initial planning handoff must use:

- `activeTaskId: null`
- `currentPhase: planning`
- `ownerRole: planner`
- `taskStatus: all tasks idle`

During implementing, testing, or reviewing, these header values should summarize the current truth-source state. Scripts may check the structural presence of fields, but LLM review remains responsible for semantic quality.

## Required Sections

Every active plan handoff must contain these sections:

- `## Current Status`
- `## Role Handoff`
- `## Risks`
- `## Next Action`

The sections are recovery evidence only. They must not introduce a task list, change the workflow phase, mark task completion, or replace `workflow-state.nextAction`.

## Role Handoff Shape

The `## Role Handoff` section must include:

- `fromRole`
- `toRole`
- `reason`
- `stateSource`

`stateSource` should name `workflow-state.json and tasks.json`. Handoff prose can explain the transition, but state writes still go through `state-write.py` and task writes still go through `update-task.py`.

## Lifecycle Transaction Entries

Lifecycle tools append transaction entries after the initial sections. Each entry starts with:

```md
## Lifecycle Transaction - <ISO-8601 timestamp>

- action: <transition action>
- taskId: <TASK-ID or null>
- phase: <before phase> -> <after phase>
- role: <before role> -> <after role>
- stateSource: workflow-state.json and tasks.json
- nextAction: <single atomic next action>
```

Transaction entries are an audit trail. They do not authorize state by themselves; the authoritative state remains `workflow-state.json` and `tasks.json`.

## Script Boundary

`lint-harness.py` may enforce deterministic structure for active plan `handoff.md`:

- required header fields exist;
- required sections exist;
- role handoff fields exist.

It must not score prose quality, infer task completion, or decide whether a handoff is semantically complete. Those judgments stay with the LLM and task review process.
