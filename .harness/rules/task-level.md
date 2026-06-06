# task-level.md

Task levels are classified by execution-control complexity, not by business label or file-count size.

| Level | Name | Criteria | Plan Shape |
|---|---|---|---|
| L0 | direct-patch | Local, low-risk direct patch work that does not need formal planning, but still needs minimal deterministic verification. | Do not create a plan; `activePlanRef = null`, `activeTaskId = null`. |
| L1 | verified-fix | Limited-scope fix work that must be confirmed by targeted tests or reproducible verification. | Do not create a plan; `activePlanRef = null`, `activeTaskId = null`. |
| L2 | planned-task | Work that must be planned before execution, with explicit completion criteria, verification, recoverable state, and a single active task during execution. | Must have an active plan package. |
| L3 | decomposed-epic | Complex work that cannot converge safely as one task and must be split into multiple subtasks or sequential phase plans. | Must have an active plan package; split into sequential plans when needed. |

## Boundary Rules

- Task level is the entry classification for workflow shape; it does not replace the state-transition rules in `.harness/rules/workflow-lifecycle.md`.
- L0/L1 still require verification and review gates, but do not create `work/plans/active/<PLAN-ID>/`.
- L2/L3 planning, implementing, testing, reviewing, and archiving must align through the active plan package, `tasks.json`, and workflow state.
- Testing, review, handoff, commit, and architecture impact are gates or audit actions; raising task level does not make them standalone tasks.
