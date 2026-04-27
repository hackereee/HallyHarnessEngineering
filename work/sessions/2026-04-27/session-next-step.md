# Session Next Step

## Context

- Repo: LearnHarnessEngineering
- Date: 2026-04-27
- Recent completed commits:
  - `3f9ee3d` 新增生命周期流转事务协调器
  - `b321a38` 迁移 Harness 测试目录
  - `60d6c5b` 补齐归档闭环
- Current lifecycle coverage:
  - `session-start.py` handles session bootstrap and audit snapshot.
  - `lifecycle-transaction.py` coordinates `activate-next`, `start-testing`, `start-review`, `review-failed`, and `review-passed`.
  - `archive-plan.py` closes L2/L3 `archiving -> archived` after Agent-written `closure.md`.
  - Tests live under `.harness/tests/`.

## Decision

The best next engineering action is to close the L0/L1 lifecycle gap before implementing the unified CLI entrypoint.

```text
.harness/scripts/complete-workflow.py
```

The unified CLI should come after this, otherwise it will expose `archive-plan` as the only formal close action and harden the incorrect model that only L2/L3 workflows can be closed.

## Rationale

- `archive-plan.py` only handles L2/L3 active plan package migration.
- L0/L1 workflows have no `plan.md` / `tasks.json` / `closure.md`; their audit anchor is `workflowId` and their completion evidence belongs in the session record.
- `workflow-lifecycle.md` says L0/L1 should end as `workflowStatus=completed`, but there is no dedicated script gateway or regression test for that transition.
- Backlog management, review block enrichment, handoff-rules, and the unified CLI are lower priority than making every task level closable.

## Proposed Scope

Implement a thin completion gateway for direct workflows:

- Add `.harness/scripts/complete-workflow.py`.
- Add `.harness/tests/test_complete_workflow.py`.
- Allow only L0/L1 shape: `activePlanRef=null`, `activeTaskId=null`, no active plan directory.
- Require a reviewed workflow state and explicit verification evidence from the caller.
- Run `lint-harness.py` and `validate-state.py` before and after completion.
- Use `state-write.py` to set `workflowStatus=completed`, preserve `activePlanRef=null` and `activeTaskId=null`, and set `nextAction="开启下一个 workflow"`.
- Update `workflow-lifecycle.md`, `archive-rules.md`, `architecture.md`, `session-start.py` required assets, and tests.

## Next Action

Write a failing `.harness/tests/test_complete_workflow.py` covering L0/L1 completion and rejecting plan-backed workflows.
