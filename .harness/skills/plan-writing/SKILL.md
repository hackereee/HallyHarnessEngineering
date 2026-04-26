---
name: plan-writing
description: Use when turning a requirement, backlog item, or approved design into Harness L2/L3 plan artifacts, or revising/materializing an approved Harness plan in a repository with .harness.
---

# Plan Writing

## Overview

Produce a complete Harness active plan package for L2/L3 work:

```text
work/plans/active/<PLAN-ID>/
├─ plan.md
├─ tasks.json
└─ handoff.md
```

`plan.md` is the planning truth source, `tasks.json` is the task execution truth source, and `handoff.md` is only a recovery summary. Plan writing stops before task activation.

## Read First

Read these before creating or revising a plan package:

- `harness-design/architecture.md`
- `harness-design/task-level.md`
- `.harness/rules/workflow-lifecycle.md`
- `learning-notes/scripts-vs-llm.md`
- `learning-notes/tasks-workflow-gates.md`
- `.harness/schemas/tasks.schema.json`
- `.harness/templates/plan.template.md`
- `.harness/templates/handoff.template.md`

## When to Use

Use this skill for:

- Turning a requirement, backlog item, or approved design into an L2/L3 Harness plan.
- Revising an active Harness plan and rematerializing `tasks.json`.
- Materializing an already confirmed `plan.md` task contract into `tasks.json` and `handoff.md`.

Do not use this skill for:

- L0/L1 direct work.
- Executing an existing task.
- Activating the next task.
- Testing, reviewing, or archiving a plan.

If the work is L0/L1, do not create `work/plans/active/<PLAN-ID>/`.

## Script Boundary

Use `.harness/scripts/materialize-tasks.py` for deterministic extraction and validation:

```bash
python3 .harness/scripts/materialize-tasks.py work/plans/active/<PLAN-ID>/plan.md --out work/plans/active/<PLAN-ID>/tasks.json --schema .harness/schemas/tasks.schema.json
```

Only call it after `plan.md` contains confirmed structured task contracts. The script:

- Parses anchor-backed task contract sections.
- Writes only `tasks.json`.
- Validates `tasks.schema.json`, `taskId`, `planSection`, `dependsOn`, file boundaries, acceptance, and verification.
- Leaves every task `status = "idle"` and `ownerRole = "developer"`.

It does not judge requirement scope, invent tasks from free text, activate tasks, update verification results, or write `workflow-state.json`.

## Templates

Harness artifact templates belong under `.harness/templates/`, not inside this skill.

- Use `.harness/templates/plan.template.md` for the required plan structure and parseable task contract syntax.
- Use `.harness/templates/handoff.template.md` for the recovery summary shape.
- Use `.harness/templates/tasks.template.json` only as the schema-valid task manifest sample; do not hand-write active `tasks.json` from it.

Skill-local files are only for skill instructions or large examples, not Harness artifact contracts.

## Flow

### 1. Pre-write Confirmation

Classify the work:

- L0/L1: no plan package.
- L2: one active plan package.
- L3: split into sequential phase plans unless one active plan can produce an independently verifiable result.

Ask only blocking questions. Blocking uncertainty includes unclear scope, unclear file boundaries, unverifiable acceptance, missing verification, uncertain task dependencies, or an L2/L3 classification dispute.

Before writing files, give a concise write summary:

- `planId` and target path.
- Task level.
- Scope and non-scope.
- File boundaries.
- Task list with dependencies, acceptance, and verification.
- Risks and open questions.
- Statement that the next step will materialize the complete package.

Continue only after the summary is confirmed or the existing `plan.md` has already been approved for materialization.

### 2. Atomic Materialization

Write the active package as a unit:

1. Ensure there is no conflicting active plan directory.
2. Create `work/plans/active/<PLAN-ID>/`.
3. Write `plan.md` using `.harness/templates/plan.template.md` structure.
4. Run `materialize-tasks.py` to generate `tasks.json`.
5. Write `handoff.md` using `.harness/templates/handoff.template.md` shape.

Hard rules:

- Do not leave only `plan.md` under `work/plans/active/<PLAN-ID>/`.
- Do not hand-write `tasks.json` when `materialize-tasks.py` can parse the plan.
- Do not create checkbox execution state in `plan.md`.
- Keep the task contract section at the end of `plan.md`; the current materializer reads task bodies until the next task anchor.
- Do not add fields unsupported by schema, such as `review`.
- Do not activate the first task.
- Do not write `workflow-state.json` directly.

### 3. Post-write Validation

Run the materialization command and relevant template/schema tests. At minimum, verify:

- `tasks.json` is valid JSON and passes `.harness/schemas/tasks.schema.json`.
- Every `taskId` is unique.
- Every `planSection` points to an anchor in `plan.md`.
- Every `dependsOn` references an existing task.
- Every task has file boundaries, acceptance, and verification commands or checks.
- Every task is initially `idle`.
- `handoff.md` describes planning/pre-activation state, not an active task.

## Plan Contract Rules

Each task contract in `plan.md` must follow this parseable shape:

```md
<a id="task-001-descriptive-anchor"></a>

### TASK-001: Descriptive title

Goal: One concrete delivery goal.

Files:
- Create: `exact/path`
- Modify: `exact/path`
- Test: `exact/path`

Depends on: []

Acceptance:
- Concrete acceptance statement.

Verification:
- Run: `exact command`
- Check: concrete manual or structural check.
```

Task contracts must not include `TBD`, `TODO`, vague work such as "完善逻辑", missing paths, or generic verification such as "manual test passed".

## Lifecycle Boundary

Task activation belongs to `.harness/rules/workflow-lifecycle.md`.

After plan writing:

- `tasks.json` contains only idle tasks.
- `workflow-state.activeTaskId` remains `null` until lifecycle activation.
- `workflow-state.currentPhase` remains `planning` until lifecycle activation.
- The suggested next action is to activate the first eligible idle task through lifecycle rules and `state-write.py`.

Testing and review are workflow gates. Never create separate tasks whose only purpose is "test" or "review".

## Self-Review

Before claiming the package is ready, check:

- L0/L1 did not create a plan package.
- L2/L3 produced `plan.md`, `tasks.json`, and `handoff.md` together.
- There is only one active plan directory.
- Scope, non-scope, files, tasks, dependencies, acceptance, and verification are covered.
- `plan.md` has stable anchors and no execution checkboxes.
- `tasks.json` has no schema-unsupported fields.
- `handoff.md` is a recovery summary and names state truth sources.
- No task is active and `workflow-state.json` was not edited directly.
