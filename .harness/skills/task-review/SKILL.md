---
name: task-review
description: Use when reviewing an active Harness task and producing the structured review gate summary for tasks.json.
---

# Task Review

## Overview

Produce a compact, structured review gate result for one active L2/L3 task.

The output is intended to be written through `.harness/scripts/update-task.py`. This skill must not directly edit `tasks.json` or `workflow-state.json`.

## Inputs

Read these before producing a review result:

- `work/workflow-state.json`
- `work/plans/active/<PLAN-ID>/plan.md`
- `work/plans/active/<PLAN-ID>/tasks.json`
- The implementation diff or changed files
- Verification evidence from the testing gate
- `.harness/rules/workflow-lifecycle.md`
- `learning-notes/tasks-workflow-gates.md`
- The plan's `Architecture Impact` section and any architecture files touched by the task

Review only the current `activeTaskId`. If there is no active task, stop and report that this skill is only for plan-backed task review.

## Rubric

Score from 0 to 100. `review-rubric-v1` passes at 85.

Check these categories:

- Task acceptance is satisfied.
- Verification evidence is present and relevant.
- Schema, template, script, and test changes are synchronized.
- Writes go through the correct gateways: `update-task.py` for `tasks.json`, `state-write.py` for `workflow-state.json`.
- Lifecycle invariants hold: testing and review are gates, not tasks; only one active task exists.
- `nextAction` remains a single atomic action.
- Architecture Impact is correct: target project changes update or preserve root `ARCHITECTURE.md` intentionally, and Harness framework changes update or preserve `.harness/ARCHITECTURE.md` intentionally.
- Archive or completion path remains consistent with task level.
- No unrelated refactor or runtime-state shortcut was introduced.

## Findings

Use these severities:

- `critical`: Harness invariant violation, data loss risk, direct state bypass, or task/review modeling error. Always blocking.
- `important`: Acceptance, verification, lifecycle, or regression risk that should block unless explicitly deferred.
- `minor`: Non-blocking cleanup, wording, or maintainability note.

For every finding, include:

- `severity`
- `blocking`
- `summary`
- Optional `artifactRef`
- Optional `recommendation`
- `deferReason` when an important finding is non-blocking

Critical findings must use `blocking = true`. Minor findings must use `blocking = false`. Important findings with `blocking = false` must explain why they can move to handoff, backlog, or closure.

## Verdict

Return one of:

- `passed`: score is at least 85, review checks are present, no critical finding exists, and no blocking important finding exists.
- `failed`: score is below 85, a critical finding exists, or an important finding is blocking.

Do not use score alone to pass a task. Blocking findings override the score.

## Output Shape

Return a JSON object matching the task `review` field:

```json
{
  "score": 90,
  "threshold": 85,
  "lastResult": "passed",
  "rubricVersion": "review-rubric-v1",
  "checks": [
    "task acceptance is satisfied",
    "verification evidence is present",
    "lifecycle invariants hold"
  ],
  "findings": [],
  "reportRef": "work/sessions/2026-04-27/session-review.md"
}
```

Detailed prose belongs in `work/sessions/...`, `handoff.md`, or `closure.md`; keep `tasks.json` as the compact gate summary.

## Applying The Result

After producing the JSON, the caller should write it through `update-task.py`, for example:

```bash
python3 .harness/scripts/update-task.py \
  --tasks work/plans/active/<PLAN-ID>/tasks.json \
  --task <TASK-ID> \
  --review-score 90 \
  --review-last-result passed \
  --review-check "task acceptance is satisfied" \
  --review-check "verification evidence is present" \
  --review-report-ref work/sessions/2026-04-27/session-review.md
```

For findings, pass each finding via `--review-finding-json '<json object>'`.

Do not run `lifecycle-transaction.py review-passed` until the structured review result has been written and `review.lastResult = "passed"`.
