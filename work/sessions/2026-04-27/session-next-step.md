# Session Next Step

## Context

- Repo: LearnHarnessEngineering
- Date: 2026-04-27
- Recent completed commits:
  - `60d6c5b` 补齐归档闭环
  - `5326858` 记录下一步会话决策
  - `93c2c58` 补齐 L0/L1 workflow 收口
  - `ccc8742` 新增 Harness 统一入口
- Current lifecycle coverage:
  - `session-start.py` handles session bootstrap and audit snapshot.
  - `lifecycle-transaction.py` coordinates `activate-next`, `start-testing`, `start-review`, `review-failed`, and `review-passed`.
  - `archive-plan.py` closes L2/L3 `archiving -> archived` after Agent-written `closure.md`.
  - `complete-workflow.py` closes L0/L1 `reviewing -> completed` with session audit evidence.
  - `harness` provides the unified script entrypoint for lifecycle commands.
  - Tests live under `.harness/tests/`.
- Current gap:
  - `learning-notes/tasks-workflow-gates.md` already defines testing/review as workflow gates whose structured results should be written back to the current task.
  - `tasks.schema.json` currently has `verification` but no structured `review` block.
  - `update-task.py` and `lifecycle-transaction.py review-passed` can move a task to `done` once verification has passed, without a machine-checkable `review.lastResult = "passed"` condition.
  - A pure pass/fail review field is too coarse for Harness Engineering: it cannot distinguish high-quality implementation, non-blocking observations, blocking findings, and invariant violations.

## Decision

The best next engineering action is to implement a structured task-level review gate with rubric scoring and blocking findings:

```text
review passed =
  score >= threshold
  AND no critical findings
  AND no blocking important findings
```

This should come before backlog schema, handoff-rules, or check-env work.

## Rationale

- Review is already modeled as a workflow gate, not a task; the missing piece is structured evidence on the active task.
- `done` should mean implementation, verification, and review have all passed. Today the machine gate only enforces verification and dependencies.
- This is a lifecycle correctness gap, not just documentation polish. It affects when `review-passed` may mark a task complete and when a plan may enter archiving.
- A score is useful as a quality signal, but score alone must not authorize completion. A task with a high average score can still violate a hard Harness invariant such as bypassing `state-write.py` or modeling testing/review as tasks.
- Critical findings are one-vote vetoes. Important findings should block by default unless the review result explicitly marks them non-blocking and explains why they can move to backlog or handoff.
- Backlog schema is intake-side work, handoff-rules improve recovery summaries, and check-env improves ergonomics. None of them closes the task completion invariant as directly as structured review.

## Review Skill Direction

Reference `superpowers/requesting-code-review` for the review discipline, but adapt it to Harness:

- Borrow the input shape: what was implemented, plan or task requirements, base/head diff, and explicit description.
- Borrow the severity model: Critical, Important, Minor.
- Borrow the issue format: file or artifact reference, what is wrong, why it matters, and how to fix.
- Borrow the explicit verdict: ready, ready with fixes, or not ready.
- Optimize for Harness by requiring structured output that can be written through `update-task.py`, not prose-only review.
- Optimize for Harness by adding rubric categories for schema sync, gateway usage, lifecycle invariants, task-level acceptance, verification evidence, review-as-gate modeling, `nextAction` atomicity, and archive/completion path consistency.
- Keep detailed review prose in `work/sessions/...`, `handoff.md`, or `closure.md`; keep `tasks.json` as the compact gate summary.

## Proposed Scope

- Add `review` to `.harness/schemas/tasks.schema.json` and `.harness/templates/tasks.template.json`.
- Use a compact review summary shape:

```json
{
  "review": {
    "score": 0,
    "threshold": 85,
    "lastResult": "not_run",
    "rubricVersion": "review-rubric-v1",
    "checks": [],
    "findings": [],
    "reportRef": ""
  }
}
```

- Initialize review fields in `.harness/scripts/materialize-tasks.py`, including `lastResult = "not_run"` and the default threshold.
- Extend `.harness/scripts/update-task.py` so review score, threshold, lastResult, checks, findings, and reportRef are written through the task gateway.
- Require `verification.lastResult = "passed"`, `review.lastResult = "passed"`, `review.score >= review.threshold`, no critical findings, and no blocking important findings before a task can become `done`.
- Update `.harness/scripts/lifecycle-transaction.py` so `review-failed` and `review-passed` consume structured review state instead of relying only on handoff/session prose.
- Add a Harness review skill that produces the structured review report and score, but does not directly mutate `tasks.json`.
- Update lifecycle docs, `learning-notes/tasks-workflow-gates.md`, and `.harness/skills/plan-writing/SKILL.md` so they no longer describe `review` as schema-unsupported.
- Add or update focused tests in `test_tasks_schema.py`, `test_materialize_tasks.py`, `test_update_task.py`, and `test_lifecycle_transaction.py`.

## Out Of Scope

- Do not create separate testing or review tasks.
- Do not move review prose into `tasks.json`; detailed review notes still belong in `handoff.md`, session notes, or `closure.md`.
- Do not let the review skill directly write `tasks.json` or `workflow-state.json`; scripts remain the write gateways.
- Do not treat score as sufficient for pass. Blocking findings override score.
- Do not start backlog schema, handoff-rules, or check-env in the same step.

## Next Action

Write a failing `.harness/tests/test_tasks_schema.py` assertion proving a `done` task must include a passing review gate: `review.lastResult = "passed"`, `review.score >= review.threshold`, no critical findings, and no blocking important findings.
