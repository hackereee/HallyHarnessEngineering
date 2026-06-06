# workflow-lifecycle.md

Rules and semantic conventions for `workflow-state.json`. **This file contains only semantics schemas cannot express**; structure, enums, and cross-field constraints live in `workflow-state.schema.json` and `tasks.schema.json`.

Scope: task level to state-shape mapping, workflow granularity, phase transitions, owner roles, the single-active-task invariant, task level escalation/de-escalation, and the handoff/archive connection.

Location: `.harness/rules/`. Together with schemas, `.harness/rules/task-level.md`, `validate-state.py`, and `state-write.py`, this file constrains the full lifecycle from workflow creation to archive.

---

## 1. Task Level to State Shape Mapping

Task levels are defined in `.harness/rules/task-level.md`. The level directly determines the legal `workflow-state.json` shape:

| Level | Trigger | activePlanRef | activeTaskId | Audit Anchor | plan.md / tasks.json |
|---|---|---|---|---|---|
| L0 / direct-patch | Local, low-risk work that does not need formal planning | `null` | `null` | `workflowId` | Do not create |
| L1 / verified-fix | Limited-scope fix that needs targeted verification | `null` | `null` | `workflowId` | Do not create |
| L2 / planned-task | Work that must be planned before execution | `./plans/active/<PLAN-ID>/plan.md` | `null` during planning/archiving; a taskId from `tasks.json` during implementing/testing/reviewing | `activeTaskId` during execution; `workflowId` + `activePlanRef` during planning/archiving | Must create |
| L3 / decomposed-epic | Work that must be split into multiple subtasks or phase plans | Same, with each phase as an independent plan | Same | Same | Must create; may require sequential plans |

**Invariants**:

- During L0/L1, `work/plans/active/` must be empty. Any residue is a state inconsistency; Agents review it today and `lint-harness.py` inspects it.
- During L2/L3, the directory pointed to by `activePlanRef` must contain `plan.md` and `tasks.json`.
- Every level must write `ownerRole` in `workflow-state.json`. L0/L1 workflows have no `tasks.json`, so only `workflow-state.ownerRole` can express the current workflow gate owner.

---

## 2. Workflow Granularity

A workflow is a **task-level container**: one workflow corresponds to one complete request-to-execution-to-closeout cycle.

- `workflowId` is immutable after creation and should carry task semantics for audit traceability.
  - L0/L1 recommended forms: `workflow-fix-<slug>-<yyyymmdd>-v1`, `workflow-adhoc-<yyyymmdd>-NNN`
  - L2/L3 recommended form: `workflow-plan-<NNN>-v1`
- After a workflow completes, it must transition to `completed` or `archived` before the next workflow starts. **Never reuse a workflowId for a new request.**
- At any time, `work/workflow-state.json` carries runtime state for exactly one workflow.
- `workflowStatus` currently supports only `active`, `completed`, and `archived`. `paused` is not a supported runtime state; adding pause/resume requires schema, phase transition, resume precondition, and lifecycle script tests first.

---

## 3. Phase Transitions

Legal `currentPhase` transition graph. Schemas validate enum values and current-shape constraints; transition path history belongs to rules and scripts.

```text
planning -> implementing -> testing -> reviewing -> archiving
   ^            ^                         |              |
   |            +---- review failed <-----+              |
   |            |                                        |
   |            +---- back to planning only for rescope  |
   +---------------- new workflow ----------------------+
```

**Transition preconditions**:

| Transition | Preconditions |
|---|---|
| `planning -> implementing` | L2/L3: `plan.md` and `tasks.json` are written and schema-valid; the task to activate is selected, and task state plus workflow state are ready to be written together. L0/L1: skip planning and start directly in implementing. |
| `implementing -> testing` | The current task has implementation output in a verifiable shape; commands or checks can run. |
| `testing -> reviewing` | `verification.lastResult == "passed"`. |
| `reviewing -> implementing` | Two cases: when `review.lastResult=failed`, the current task returns to implementation; when structured review passed and another executable idle task exists, the current task becomes `done` and the next task is activated. Both cases must refresh `nextAction`. |
| `reviewing -> completed` | L0/L1 only: no active plan, no active task, and verification evidence plus review summary are ready for session audit. |
| `reviewing -> archiving` | L2/L3 only: structured review passed, the current task is `done`, and the plan has no unfinished task. |
| `archiving -> archived` | L2/L3 only: the Agent has written `closure.md`; `archive-plan.py` migrates the package and sets `workflowStatus` to `archived`. |

**No jumps**: for example, `planning -> testing` skipping implementing is illegal. `state-write.py` checks transition path from before-state to after-state; schemas and `validate-state.py` only validate current shape. `reviewing -> archiving` must also make `state-write.py` read the active plan's `tasks.json` and confirm the before-state active task is `done` and all plan tasks are `done`.

**Rollback**: only `implementing -> planning` is allowed, and only with a scope-adjustment record in handoff. All other rollback is illegal.

**Terminal reset**: re-entering `active` from `completed` or `archived` is a workflow-level reset, not an ordinary phase change. Even if `currentPhase` does not change, it must go through `start-workflow.py`, which calls `state-write.py --allow-terminal-reset`, and it must explicitly write a new `workflowId`, `workflowStatus=active`, `activePlanRef`, `activeTaskId`, `currentPhase`, `ownerRole`, and `nextAction`.

In non-terminal-reset writes, `workflowId` is immutable after creation; `state-write.py` must block ordinary patches that modify it. Planned terminal reset also requires the active plan package referenced by `activePlanRef` to have passed the planning-time `Plan Review Gate`: `plan.md` must contain `## Plan Review Gate` and that section must include `Status: passed`.

**Terminal close**: closing `active` into `completed` or `archived` is not an ordinary field update. L0/L1 must use `complete-workflow.py`; L2/L3 must use `archive-plan.py`. The lower-level `state-write.py` permits terminal close only when `--allow-terminal-close` is explicit, the patch explicitly clears active refs, and `work/plans/active/` has no residual active plan.

### 3.1 Workflow ownerRole and Task ownerRole

`workflow-state.ownerRole` is the workflow-gate owner role and applies to L0-L3. It is determined by `currentPhase`:

| workflow phase | workflow-state.ownerRole | Meaning |
|---|---|---|
| `planning` | `planner` | Planner creates or revises the plan package. |
| `implementing` | `developer` | Developer implements the current workflow work unit. |
| `testing` | `tester` | Tester runs verification commands or checks. |
| `reviewing` | `reviewer` | Reviewer checks acceptance, engineering boundaries, and Harness invariants. |
| `archiving` | `developer` | Developer performs archive actions, creates closure, and completes state closeout. |

`tasks.json` is the task-level execution truth source and must express who owns the current task. When L2/L3 has an active task, `workflow-state.currentPhase`, `workflow-state.ownerRole`, and the active task's `status` / `ownerRole` should remain aligned:

| workflow phase | workflow-state.ownerRole | task.status | task.ownerRole | Meaning |
|---|---|---|---|---|
| `planning` | `planner` | `idle` | `developer` | Plan package exists but no task is active; `task.ownerRole` shows who will receive it after activation. |
| `implementing` | `developer` | `implementing` | `developer` | Developer implements the active task. |
| `testing` | `tester` | `testing` | `tester` | Tester runs verification commands or checks. |
| `reviewing` | `reviewer` | `reviewing` | `reviewer` | Reviewer produces the structured `review` gate result. |
| `archiving` | `developer` | no active task; all plan tasks are `done` | each task keeps its final owner role | The plan has no unfinished task, `activeTaskId = null`, and workflow is archiving. |

State/role write requirements:

- Every phase transition must refresh `workflow-state.ownerRole`.
- `planning -> implementing`: the selected task changes from `idle/developer` to `implementing/developer`.
- `implementing -> testing`: the current task changes to `testing/tester`.
- `testing -> reviewing`: the current task changes to `reviewing/reviewer`.
- `reviewing -> implementing`: the current task must already have `review.lastResult = "failed"`, then it returns to `implementing/developer` with a review-failed summary.
- After `reviewing` passes: the current task must already have a passed structured `review` gate before it can be marked `done`. If another executable task exists, activate it under the single-active-task rule; if not, enter `archiving` with `activeTaskId = null`.

`handoff.md` may record role handoff summaries, but it is not a truth source. Truth remains `workflow-state.json` and `tasks.json`.

### 3.2 Script and Artifact Boundaries for Phase Transitions

A phase transition is not just a change to `workflow-state.currentPhase`. For L2/L3, every `planning -> implementing -> testing -> reviewing` transition must maintain four artifact families:

| Artifact | Responsibility | Write Boundary |
|---|---|---|
| `work/workflow-state.json` | workflow phase, role, active task, next step | Only through `state-write.py` |
| `work/plans/active/<PLAN-ID>/tasks.json` | task status, role, verification result, review result, blocked reason | Only through `update-task.py`; Agents must not hand-edit runtime task state |
| `work/plans/active/<PLAN-ID>/handoff.md` | phase transition and role handoff summary | Agent-owned semantic summary; must not replace state/tasks |
| `work/sessions/YYYY-MM-DD/session-<id>.md` | command output, review process, exception analysis, session audit | Agent records reproducible evidence |

Implemented scripts:

- `session-start.py`: session startup preflight. It checks key Harness artifacts and environment availability, runs `lint-harness.py`, creates the first L0/L1 state from template only when `workflow-state.json` is missing and no active plan exists, then runs `validate-state.py` and writes a session audit snapshot. It must not modify existing state, activate tasks, or advance phase.
- `materialize-tasks.py`: generates initial `tasks.json` from a confirmed `plan.md` task contract. All tasks start as `idle/developer`, `review.lastResult = "not_run"`, and unknown or cyclic `dependsOn` entries are blocked.
- `update-task.py`: task state write gateway for `tasks.json`. It updates task `status`, `ownerRole`, `currentStep`, `nextAction`, `verification`, `review`, and `blockedReason`, and validates `tasks.schema.json` plus done preconditions before writing.
- `select-next-task.py`: read-only selector. It chooses the next executable `idle` task by `dependsOn` and `status`, or outputs a state patch suggestion to enter `archiving` when all plan tasks are `done`. It only outputs structured suggestions for `update-task.py` / `state-write.py`; it does not write `tasks.json` or `workflow-state.json`.
- `state-write.py`: only write gateway for `workflow-state.json`; terminal reset and terminal close require explicit flags and preconditions.
- `start-workflow.py`: starts a new `active` workflow from `completed` or `archived`. It does not write state directly; it calls `state-write.py --allow-terminal-reset`. Direct L0/L1 workflows enter `implementing/developer`; planned L2/L3 workflows bind an existing active plan package and enter `planning/planner`.
- `lifecycle-transaction.py`: lifecycle transition coordinator. It runs `lint-harness.py` / `validate-state.py` preflight, dry-runs in an isolated copy, calls `update-task.py` and `state-write.py`, appends `handoff.md`, and runs postflight. It does not replace lower-level write gateways. Current actions include `activate-next`, `start-testing`, `start-review`, `review-failed`, and `review-passed`.
- `commit-task.py`: task completion commit gate. It runs only after `lifecycle-transaction.py review-passed`, reads `workflow-state.json` and the active plan's `tasks.json`, confirms the target task is `done` and verification/review both passed, then performs `git add -A` and `git commit`. It does not write state/tasks and does not replace lifecycle transition.
- `archive-plan.py`: archive tool. It is used only when `currentPhase=archiving`; it requires an Agent-written complete `closure.md`, validates that all tasks are `done`, migrates the active plan package, and closes workflow state.
- `complete-workflow.py`: L0/L1 direct workflow closeout tool. It requires `activePlanRef=null`, `activeTaskId=null`, no active plan directory, and `reviewing/reviewer`. The caller must provide verification evidence and a review summary. It closes workflow state through `state-write.py` and writes completion evidence to the session audit JSONL.
- `validate-state.py`: validates workflow state and active-task cross-file consistency.
- `lint-harness.py`: read-only inspection for directory structure and global invariants. It is suitable as preflight/postflight for session start, `planning -> implementing`, active task switching, and archiving.

Standard phase transition sequence. Any write to `workflow-state.json` must eventually go through `state-write.py`; any write to `tasks.json` must go through `update-task.py`.

| Transition | tasks.json Change | workflow-state.json Change | Other Artifacts |
|---|---|---|---|
| `planning -> implementing` | selected `idle/developer` task becomes `implementing/developer`; task-level `nextAction` is written | `currentPhase=implementing`, `ownerRole=developer`, `activeTaskId=<TASK-ID>`, workflow `nextAction` refreshed | Prefer `lifecycle-transaction.py activate-next`; append planner-to-developer handoff |
| `implementing -> testing` | current task becomes `testing/tester`; `verification.lastResult` stays `not_run` or `failed` | `currentPhase=testing`, `ownerRole=tester`, same `activeTaskId`, refreshed `nextAction` | Record executable verification commands or checks |
| `testing -> reviewing` | current task must first write `verification.lastResult=passed`, then become `reviewing/reviewer` | `currentPhase=reviewing`, `ownerRole=reviewer`, same `activeTaskId`, refreshed `nextAction` | Session audit records verification evidence summary |
| `reviewing -> implementing` (review failed) | current task must already have `review.lastResult=failed`, then returns to `implementing/developer`, preserving or refreshing task `nextAction` | `currentPhase=implementing`, `ownerRole=developer`, same `activeTaskId`, refreshed `nextAction` | Handoff or session records review findings summary |
| `reviewing -> implementing` (next task) | current task satisfies done preconditions and becomes `done`; next executable task becomes `implementing/developer` | `currentPhase=implementing`, `ownerRole=developer`, `activeTaskId=<NEXT-TASK-ID>`, refreshed `nextAction` | `select-next-task.py` chooses the next task; then run `commit-task.py --task <COMPLETED-TASK-ID>` |
| `reviewing -> archiving` | current task satisfies done preconditions and becomes `done`; every plan task is `done` | `currentPhase=archiving`, `ownerRole=developer`, `activeTaskId=null`, refreshed `nextAction` | First run `commit-task.py --task <COMPLETED-TASK-ID>`, then Agent writes `closure.md` and runs `archive-plan.py` |
| `reviewing -> completed` (L0/L1) | no `tasks.json` change | `workflowStatus=completed`, `activePlanRef=null`, `activeTaskId=null`, keep `currentPhase=reviewing` / `ownerRole=reviewer` as final gate shape, refreshed `nextAction` | `complete-workflow.py` records verification evidence and review summary |
| terminal -> new active workflow | direct L0/L1 has no `tasks.json`; planned L2/L3 requires active plan package and postflight lint | new `workflowId`, `workflowStatus=active`, explicit reset of `activePlanRef`, `activeTaskId`, `currentPhase`, `ownerRole`, and `nextAction` | Must go through `start-workflow.py`, which calls `state-write.py --allow-terminal-reset`; direct state edits are forbidden |

The structured review gate is encoded in `tasks.schema.json`: `review.lastResult = "passed"` can support task `done` only when `score >= threshold`, review `checks` exist, no critical finding exists, and no blocking important finding exists. A `minor` finding can only be non-blocking cleanup. Detailed review prose belongs in `work/sessions/...`, `handoff.md`, or `closure.md`; `tasks.json` stores only the compact gate summary.

### 3.3 Task Completion Commit Gate

After every L2/L3 task successfully completes `lifecycle-transaction.py review-passed` and postflight, run `commit-task.py --task <COMPLETED-TASK-ID>` to create a task completion commit before starting another implementation or writing archive closure.

Gate position:

1. Complete verification and structured review for the current task.
2. Run `lifecycle-transaction.py review-passed` to mark the current task `done`.
3. If another task exists, `review-passed` may activate it; if not, it enters `archiving`.
4. Immediately run `commit-task.py --task <COMPLETED-TASK-ID>`.
5. Then start the next task implementation, or write `closure.md` and archive the plan.

The commit may include state changes produced by `review-passed`, appended `handoff.md`, and `workflow-state.json` / `tasks.json` changes caused by next-task activation. This keeps the completed task and the workflow pointer to the next step in one audited commit. Do not start the next implementation before committing the completed task, or the commit boundary will mix two task deliverables.

`commit-task.py` deterministic checks:

- The target task must exist in the current active plan's `tasks.json`.
- The target task must have `status=done`.
- `verification.lastResult` must be `passed`, and commands or checks must exist.
- `review.lastResult` must be `passed`, `score >= threshold`, review `checks` must exist, and there must be no critical finding or blocking important finding.
- The worktree must contain a committable diff; an empty commit is not task completion and must be blocked.

Commit gate is not an independent task and does not change task status. Git history is the commit audit source; `tasks.json` does not store commit hashes.

Before archive, `archive-plan.py` must recheck the commit boundary: no uncommitted changes may exist except the current plan's `closure.md`. Otherwise, the `commit-task.py` gate is not closed and archive must be blocked.

---

## 4. Single Active Task Invariant

During L2/L3 implementing/testing/reviewing, there must be **exactly one activeTaskId**.

- Schema enforces "plan-driven plus execution phase implies activeTaskId is a string."
- Rule-level addition: `activeTaskId` must correspond to a task in `tasks.json` whose `status` is one of `implementing`, `testing`, or `reviewing`. Tasks with `idle`, `done`, or `blocked` must not be `activeTaskId`.
- `workflow-state.ownerRole` must equal the active task's `ownerRole`.
- Switching `activeTaskId` must go through `state-write.py`; the old task must first be written to `done` or `blocked` through `update-task.py`. **Two active tasks are forbidden.**

L0/L1 has no active-task invariant: `activeTaskId` must be null, the work unit is described by `workflowId`, and current ownership is described by `workflow-state.ownerRole`.

---

## 5. Cases Where activeTaskId Must Be null

Summary:

| Case | activePlanRef | activeTaskId | Source |
|---|---|---|---|
| L0/L1 throughout | `null` | `null` | This file section 1 / schema allOf |
| L2/L3 in `planning` phase | active plan path | `null` | schema allOf |
| L2/L3 in `archiving` phase | active plan path | `null` | schema allOf |
| `workflowStatus = completed` | `null` | `null` | schema allOf |
| `workflowStatus = archived` | `null` | `null` | schema allOf |

`activePlanRef = null` / `activeTaskId = null` does not mean nobody owns the work. Every listed case still requires a legal `workflow-state.ownerRole`.

---

## 6. Task Level Escalation and De-escalation

If execution reveals that the original task level is wrong:

- **L0 -> L1**: add verification only; state shape does not change and no migration is needed.
- **L1 -> L2**: stop and enter planning. First create and validate `<PLAN-ID>/plan.md` plus `tasks.json` under `work/plans/active/`; then apply a patch through `state-write.py` to set `activePlanRef`, `currentPhase=planning`, and `ownerRole=planner`. Task activation happens only after that. **Do not keep implementing while backfilling a plan.**
- **L2 -> L3**: split the current plan or create follow-up plans, advancing sequentially. There is still only one active plan at a time.
- **L2 -> L1 de-escalation**: allowed only if the plan and `tasks.json` have not yet carried substantive content. Archive the current plan directory, set state `activePlanRef` to null, and return to L1 shape.

Any escalation or de-escalation is a state change and must be written through `state-write.py` and recorded in session audit.

---

## 7. Completion Criteria

An L2/L3 task may enter `done` only when all conditions hold:

1. `verification.lastResult == "passed"`.
2. At least one of `verification.commands` or `verification.checks` is non-empty; otherwise verification is undefined and `done` is forbidden.
3. `review.lastResult == "passed"`, `review.score >= review.threshold`, and there is no critical finding or blocking important finding.
4. Every task in `dependsOn` is `done`; schema does not enforce this, but `update-task.py` checks it when writing `done`, and `select-next-task.py` checks candidate dependencies when selecting the next task.

L0/L1 workflow completion criteria:

1. `activePlanRef = null` and `activeTaskId = null`.
2. `work/plans/active/` has no residual active plan directory.
3. The current workflow has reached the `reviewing/reviewer` gate.
4. Session audit contains verification evidence and review summary.
5. Session audit contains architecture impact summary explaining whether root `ARCHITECTURE.md` and Harness framework architecture were updated or why no update was needed.
6. `workflowStatus` transitions to `completed` through `complete-workflow.py` / `state-write.py`, and `nextAction` is replaced with the first action for the next workflow.

Starting the next workflow requires:

1. The current workflow is already in `workflowStatus in {completed, archived}`.
2. Current state holds no `activePlanRef` or `activeTaskId`.
3. The new workflow uses a new `workflowId`; reusing the old workflowId is forbidden.
4. Direct L0/L1 starts with `currentPhase=implementing`, `ownerRole=developer`, `activePlanRef=null`, `activeTaskId=null`.
5. Planned L2/L3 starts with `currentPhase=planning`, `ownerRole=planner`, and `activePlanRef` pointing to an existing active plan package.
6. The write must be coordinated by `start-workflow.py` and persisted through `state-write.py --allow-terminal-reset`.

---

## 8. nextAction and Lifecycle

`nextAction` is where schema and this rule intersect:

- Schema: `minLength: 1`, `maxLength: 200`.
- Rule and `validate-state.py` heuristic: one atomic sentence; multi-step verbs and vague high-level goals are forbidden.
- Lifecycle constraint: every phase transition must refresh `nextAction` and `ownerRole`. `state-write.py` warns when `nextAction` is unchanged, and warns when a patch does not explicitly include `ownerRole`.

---

## 9. Architecture Impact Gate

Architecture Impact is a workflow gate, not a standalone task. It requires the Agent to decide during planning, review, completion, or closure whether the work makes architecture documentation inaccurate.

Judgment boundary:

- If target project business modules, dependencies, data flow, runtime topology, external interfaces, or project boundaries changed, check whether root `ARCHITECTURE.md` needs an update.
- If Harness schemas, rules, scripts, templates, skills, lifecycle model, or `.harness/` framework boundaries changed, check whether `.harness/ARCHITECTURE.md` needs an update.
- `work/` workflow-state, plans, tasks, handoff, and session audit are runtime or audit evidence only. They are not architecture-document update reasons unless lifecycle rules themselves changed.

Write boundary:

- L2/L3 planning: `plan.md` must contain `Architecture Impact` with expected impact.
- L2/L3 task review: review checks must cover actual Architecture Impact. Documentation drift should be a blocking finding unless there is an explicit `deferReason`.
- L2/L3 archiving: `closure.md` must contain `Architecture Impact` with final update/no-update reasoning. `archive-plan.py` checks section presence only; it does not judge semantic quality.
- L0/L1 completion: `complete-workflow.py` must record architecture impact summary in session completion audit.

Only when updating architecture documentation itself is a concrete deliverable may it be modeled as a task. Do not create a process task whose only purpose is "decide whether architecture changed."

---

## 10. Handoff and Archive Connection

- Phase transitions, active task switches, and task-level escalation/de-escalation must append a record to `handoff.md`; see `.harness/rules/handoff-rules.md` for entry format.
- Session files written by `session-start.py` are session startup evidence and Agent semantic records only. They are not workflow or task truth sources and must not replace `workflow-state.nextAction`, `tasks.json`, or `handoff.md`.
- The final `archiving -> archived` step should first have the Agent write `closure.md`; then `archive-plan.py` migrates `plans/active/<PLAN-ID>/` to `plans/archived/<PLAN-ID>/` and uses `state-write.py` to set `workflowStatus` to `archived`.
- L0/L1 workflows have no plan, skip plan migration and `closure.md`, and use `complete-workflow.py` to close to `completed` while recording verification evidence, review summary, and architecture impact summary in session audit JSONL.
- `completed` and `archived` are not executable phases. The next item of work must create a new workflowId through `start-workflow.py` before progressing.

---

## 11. Violation Handling Quick Reference

| Violation | Detection Point | Handling |
|---|---|---|
| `activeTaskId` is non-null in L0/L1 shape | `validate-state.py` cross-file layer | Block; require setting it to null |
| `activePlanRef` points to a missing `plan.md` or sibling `tasks.json` | `validate-state.py` cross-file layer | Block; materialize a complete plan package first |
| L2/L3 execution phase `activeTaskId` is not in `tasks.json` | `validate-state.py` cross-file layer | Block; fix or reselect the task |
| Jumping `currentPhase` transition | `state-write.py` lifecycle layer | Block; require legal path |
| `reviewing -> archiving` when active task is not `done` or plan has unfinished tasks | `state-write.py` lifecycle precondition | Block; first complete structured review gate through `update-task.py` / `lifecycle-transaction.py review-passed` |
| `currentPhase` and `workflow-state.ownerRole` do not match | schema | Block; fix ownerRole by phase |
| L2/L3 active task `ownerRole` and `workflow-state.ownerRole` do not match | `validate-state.py` cross-file layer | Block; synchronize workflow and task ownership |
| Two active tasks | `select-next-task.py` + `state-write.py` + `lint-harness.py` | Selector refuses when an active task already exists; writer rejects inconsistent state; lint enforces directory/task inspection |
| Residual `plans/active/` directory with `activePlanRef = null` | `lint-harness.py` | Block; archive or restore the reference |
| L0/L1 completion used on a plan-backed workflow | `complete-workflow.py` | Block; use `archive-plan.py` instead |
| Start workflow from non-terminal state | `start-workflow.py` | Block; complete or archive the current workflow first |
| Terminal reset reuses old workflowId or does not explicitly clear active refs | `state-write.py --allow-terminal-reset` | Block; use a new workflowId and write the full state fields explicitly |
| Non-terminal-reset patch modifies workflowId | `state-write.py` | Block; workflowId is immutable, and new requests must start a new workflow |
| Planned terminal reset binds a plan without passed Plan Review Gate | `state-write.py --allow-terminal-reset` / `start-workflow.py` | Block; complete planning-time review and record `Status: passed` first |
| Terminal close lacks explicit flag or leaves active plan residue | `state-write.py --allow-terminal-close` | Block; use `complete-workflow.py` or `archive-plan.py` for closeout |
