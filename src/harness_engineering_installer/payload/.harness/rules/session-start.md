# session-start.md

`session-start.py` is the Harness session bootstrap and audit entrypoint. It prepares a new Agent session to resume the current workflow, but it is not a lifecycle transition tool.

## Allowed Startup Paths

There are exactly three startup paths:

1. validate existing state
   - If `work/workflow-state.json` exists, `session-start.py` must validate it and write a session audit file.
   - It must not modify existing workflow-state.json.

2. bootstrap missing state
   - If `work/workflow-state.json` is missing and `work/plans/active/` has no active plan directory, `session-start.py` may create the initial direct L0/L1 state from `.harness/templates/workflow-state.template.json`.
   - The bootstrapped state starts as `workflowStatus=active`, `currentPhase=implementing`, `ownerRole=developer`, `activePlanRef=null`, and `activeTaskId=null`.

3. block missing state with active plan
   - If `work/workflow-state.json` is missing but an active plan package exists, `session-start.py` must block startup.
   - The script must not infer workflow state from plan files, tasks, handoff, directory names, or previous sessions.
   - Recovery in this case is an LLM semantic decision followed by normal Harness write gateways.

## What Session Start May Do

`session-start.py` may:

- check required Harness assets;
- report environment availability;
- run `lint-harness.py`;
- create the first state only in the bootstrap path;
- run `validate-state.py`;
- create `work/plans/active`, `work/plans/archived`, and the current session directory;
- write `work/sessions/YYYY-MM-DD/session-<id>.md` as a session audit file.

## What Session Start Must Not Do

`session-start.py` must not:

- activate tasks;
- advance `currentPhase`;
- rewrite existing `workflow-state.json`;
- write `tasks.json`;
- write active plan files;
- decide whether backlog `preempt` items interrupt the current workflow;
- parse previous session files as truth sources.

## Session Audit File

The session audit file records startup evidence:

- timestamp and repo root;
- previous session reference if one exists;
- lint and validate results;
- environment checks;
- git status summary;
- current workflow fields and `nextAction`.

The session audit file is not a truth source. If it conflicts with `workflow-state.json`, `tasks.json`, or active plan files, the structured Harness artifacts win.

## Relationship To Other Rules

- Lifecycle state transitions are defined by `.harness/rules/workflow-lifecycle.md`.
- Active plan recovery summaries are defined by `.harness/rules/handoff-rules.md`.
- Archive and direct completion behavior are defined by `.harness/rules/archive-rules.md`.
- Backlog intake is defined by `.harness/rules/backlog-rules.md`.
