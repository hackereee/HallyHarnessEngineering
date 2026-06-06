# archive-rules.md

L2/L3 plan archive rules. Archiving is the final closeout action for a plan-backed lifecycle: move the completed active plan package from `work/plans/active/<PLAN-ID>/` to `work/plans/archived/<PLAN-ID>/`, and close `workflow-state.json` into the archived shape.

L0/L1 workflows do not have an active plan package and must not use `archive-plan.py`. Their closeout action is workflow completion: `complete-workflow.py` validates the direct workflow shape, records session audit evidence, and uses `state-write.py` to set `workflowStatus` to `completed`.

## Boundary

- `closure.md` is the semantic closeout owned by the LLM; scripts do not generate its full body automatically.
- `archive-plan.py` performs only deterministic validation, directory migration, and state patching.
- `workflow-state.json` is still written only through `state-write.py`; terminal close must be performed by `complete-workflow.py` or `archive-plan.py` through `state-write.py --allow-terminal-close`.
- `tasks.json` is no longer modified during archiving; every task must already be `done`.
- After entering `archiving`, run `commit-task.py --task <TASK-ID>` for the just-completed task before writing `closure.md` and running `archive-plan.py`; the task completion commit and archive commit are separate boundaries.
- `archive-plan.py` accepts a path inside the Harness root as `--root` and uses that root to locate `.harness/` and `work/`; the Git top-level may be a parent of the Harness root. Before archiving, the script checks through the Git worktree that there are no uncommitted changes except the current plan's `closure.md`. If code, `tasks.json`, `workflow-state.json`, `handoff.md`, or session evidence is still uncommitted, the task completion commit gate is not closed and archiving must be blocked.
- L0/L1 completion does not migrate directories or generate `closure.md`, but it must provide verification evidence and a review summary.

## Archive Preconditions

The archive script must block these cases:

- `workflow-state.currentPhase != "archiving"`。
- `workflow-state.ownerRole != "developer"`。
- `workflow-state.activeTaskId != null`。
- `workflow-state.activePlanRef` does not point to the target active plan's `plan.md`.
- The active plan package is missing `plan.md`, `tasks.json`, `handoff.md`, or `closure.md`.
- `closure.md` is missing any of `Delivered`, `Verification Evidence`, `Review Summary`, `Architecture Impact`, `Deviations`, or `Follow-ups`.
- `tasks.json` contains any task that is not `done`.
- Uncommitted changes other than the current plan's `closure.md` exist before archiving, or `--root` is not inside a Git repository.
- `work/plans/archived/<PLAN-ID>/` already exists.

## Archive Actions

Standard actions after the final task completes:

1. `lifecycle-transaction.py review-passed` marks the current task `done` and sets the workflow to `currentPhase=archiving`.
2. Immediately run `commit-task.py --task <TASK-ID>` to commit the task deliverables, done state, handoff record, and archiving state.
3. The Agent writes `closure.md`; its `Architecture Impact` section must record whether root `ARCHITECTURE.md` and Harness framework architecture were updated or why no update was needed.
4. Run `archive-plan.py PLAN-001`.

Standard actions for `archive-plan.py PLAN-001`:

1. Run `lint-harness.py` and `validate-state.py`.
2. Validate archive preconditions.
3. Move `work/plans/active/PLAN-001/` to `work/plans/archived/PLAN-001/`.
4. Use `state-write.py --allow-terminal-close` to set:
   - `workflowStatus = "archived"`
   - `activePlanRef = null`
   - `activeTaskId = null`
   - `nextAction = "Start the next workflow"`
5. Run `lint-harness.py` and `validate-state.py` again.

After archiving, `plan.md`, `tasks.json`, `handoff.md`, and `closure.md` inside the archived plan package together form the auditable record. The runtime truth source remains `work/workflow-state.json`.

`workflowStatus = "archived"` is a terminal state. Re-entering `active` must create a new `workflowId` through `start-workflow.py` / `state-write.py --allow-terminal-reset`; a partial `workflowStatus` patch must not reopen the old workflow.

## L0/L1 Completion Actions

Standard actions for `complete-workflow.py`:

1. Require `workflow-state.activePlanRef = null` and `workflow-state.activeTaskId = null`.
2. Require `work/plans/active/` to contain no active plan directory.
3. Require the current direct workflow to be in `currentPhase=reviewing`, `ownerRole=reviewer`, indicating that the testing/review gate has reached final review.
4. Require the caller to provide at least one verification command or check, plus a review summary and architecture impact summary.
5. Preflight that `work/sessions/YYYY-MM-DD/workflow-completions.jsonl` is writable.
6. Run `lint-harness.py` and `validate-state.py`.
7. Use `state-write.py --allow-terminal-close` to set:
   - `workflowStatus = "completed"`
   - `activePlanRef = null`
   - `activeTaskId = null`
   - `nextAction = "Start the next workflow"`
8. Append completion evidence, review summary, and architecture impact summary to `work/sessions/YYYY-MM-DD/workflow-completions.jsonl` using atomic replacement.
9. Run `lint-harness.py` and `validate-state.py` again.

`workflowStatus = "completed"` is the terminal state for a direct workflow. Re-entering `active` must create a new `workflowId` through `start-workflow.py` / `state-write.py --allow-terminal-reset`; a partial `workflowStatus` patch must not continue the old workflow.
