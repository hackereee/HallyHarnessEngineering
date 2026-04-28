<!-- harness-engineering:start -->
## Harness Engineering

This repository uses Harness Engineering for agent workflow control.

Managed block version: `harness-entrypoint-block-v1`

Read order:
1. This agent entry document.
2. Project business architecture: `ARCHITECTURE.md`.
3. Harness framework architecture: `.harness/ARCHITECTURE.md`.
4. Harness lifecycle rules: `.harness/rules/workflow-lifecycle.md`.
5. Scenario rules: `.harness/rules/session-start.md`, `.harness/rules/handoff-rules.md`, `.harness/rules/archive-rules.md`, and `.harness/rules/backlog-rules.md`.
6. Harness project contracts: `.harness/contracts/`.

Conflict priority:
- Target project rules remain valid when compatible with Harness lifecycle.
- Workflow, task, testing, review, state, commit, handoff, backlog, or archive conflicts map to Harness lifecycle.
- Report conflicts before changing user-owned prose outside this managed block.

Workflow mapping:
- startup and resume rules map to `session-start.py`.
- planning maps to `planning`.
- development maps to `implementing`.
- tests map to the `testing` gate.
- reviews map to the `reviewing` gate.
- task completion commits map to `commit-task.py`.
- L0/L1 completion maps to `complete-workflow.py`.
- L2/L3 archive maps to `archive-plan.py`.
- incoming work maps to `backlog-intake.py`.

Truth sources:
- Workflow runtime: `work/workflow-state.json`
- Task runtime: `work/plans/active/<PLAN-ID>/tasks.json`
- Planning contract: `work/plans/active/<PLAN-ID>/plan.md`
- Recovery summary: `work/plans/active/<PLAN-ID>/handoff.md`
- Project environment contract: `.harness/contracts/project-contracts.json`
- Project entrypoint contract: `.harness/contracts/project-entrypoints.json`

Write gateways:
- `workflow-state.json` is written only through `state-write.py` or lifecycle tools that call it.
- `tasks.json` is initialized through `materialize-tasks.py` and updated through `update-task.py`.
- Phase transitions use `lifecycle-transaction.py` when available.
- Backlog writes use `backlog-intake.py`.

Task modeling:
- A task is a deliverable work unit.
- Testing, review, architecture impact, commit, and handoff are gates or audit actions, not tasks.
- L0/L1 do not create plans.
- L2/L3 use one active plan and one active task during implementing/testing/reviewing.
<!-- harness-engineering:end -->
