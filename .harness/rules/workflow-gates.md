# Workflow Gates

This rule defines the boundary between deliverable tasks and workflow gates. It is a fixed `.harness/` rule asset so installed skills never depend on source-only learning material.

## Principle

`tasks.json` is the task execution truth source, but testing, review, architecture impact, commit, handoff, completion, and archive are workflow gates or audit actions. They are not standalone delivery tasks.

## Task Modeling

A task is a deliverable work unit. Do not split normal delivery into separate process tasks such as:

```text
TASK-001 Implement feature
TASK-002 Test feature
TASK-003 Review feature
```

Model the deliverable as one task and record testing/review results inside that task:

```text
TASK-001 Implement feature
```

## Plan-Time Review Gate

Plan writing includes a planning-time `Plan Review Gate`.

- This gate verifies scope, file boundaries, dependencies, acceptance, verification, and architecture impact before task materialization.
- It is recorded in `plan.md`.
- It is not `workflow-state.currentPhase = reviewing`.
- It must not be represented as a task in `tasks.json`.

`materialize-tasks.py` may run only after `plan.md` records `Plan Review Gate` with `Status: passed`.

## Testing Gate

The workflow testing phase validates the current deliverable task.

- For L2/L3, the active task records results under `verification`.
- `verification.lastResult = "passed"` is required before review can pass.
- Failed verification returns the task/workflow to implementation.
- Verification evidence must be reproducible through commands or concrete checks; generic "manual test passed" is not enough.

## Review Gate

The workflow review phase produces a compact structured result under the active task's `review` field.

- If detected target project entrypoints or tool/editor rule files explicitly define project-level review rules, the reviewer must read and apply those project-level review rules during this gate.
- Project-level review rules may tighten the review, add domain checks, or require extra evidence, but they must not weaken Harness review thresholds, bypass workflow gates, or permit direct writes around `update-task.py` / `state-write.py`.
- The detailed review report must identify the applied project-level review rule sources, or state that no explicit project-level review rules were detected.
- `review.lastResult = "passed"` requires `review.score >= review.threshold`.
- Passing review requires checks, no critical finding, and no blocking important finding.
- Critical findings are always blocking.
- Important findings are blocking unless explicitly deferred with `blocking = false` and `deferReason`.
- Minor findings are non-blocking cleanup and must use `blocking = false`.

Detailed review prose belongs in `work/sessions/...`, `handoff.md`, or `closure.md`, not in `tasks.json`.

## Done Conditions

An active task may enter `done` only when:

1. Acceptance criteria are satisfied.
2. `verification.lastResult == "passed"`.
3. `review.lastResult == "passed"`.
4. `review.score >= review.threshold`.
5. There is no critical finding and no blocking important finding.
6. All dependencies are already `done`.

For L0/L1 workflows without `tasks.json`, testing and review responsibility is still represented through `workflow-state.ownerRole`.

## Boundary Summary

`plan.md` stores the task contract, `tasks.json` stores execution state and gate evidence, `workflow-state.json` stores the current workflow phase and owner role, and scripts are the only runtime write gateways.
