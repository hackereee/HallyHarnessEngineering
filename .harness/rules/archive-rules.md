# archive-rules.md

L2/L3 plan 归档规则。归档是 lifecycle 的最后收口动作：把已完成的 active plan package 从 `work/plans/active/<PLAN-ID>/` 迁移到 `work/plans/archived/<PLAN-ID>/`，并将 `workflow-state.json` 收到 archived 形态。

## 边界

- `closure.md` 是 LLM 负责的语义收口，不由脚本自动生成完整正文。
- `archive-plan.py` 只做确定性校验、目录迁移和 state patch。
- `workflow-state.json` 仍只能经 `state-write.py` 写入。
- `tasks.json` 在归档阶段不再修改；所有 task 必须已经是 `done`。

## 归档前置条件

归档脚本必须阻断以下情况：

- `workflow-state.currentPhase != "archiving"`。
- `workflow-state.ownerRole != "developer"`。
- `workflow-state.activeTaskId != null`。
- `workflow-state.activePlanRef` 不指向目标 active plan 的 `plan.md`。
- active plan package 缺少 `plan.md`、`tasks.json`、`handoff.md` 或 `closure.md`。
- `closure.md` 缺少 `Delivered`、`Verification Evidence`、`Review Summary`、`Deviations`、`Follow-ups` 中任一章节。
- `tasks.json` 中存在非 `done` task。
- `work/plans/archived/<PLAN-ID>/` 已存在。

## 归档动作

`archive-plan.py PLAN-001` 的标准动作：

1. 运行 `lint-harness.py` 与 `validate-state.py`。
2. 校验归档前置条件。
3. 将 `work/plans/active/PLAN-001/` 迁移到 `work/plans/archived/PLAN-001/`。
4. 通过 `state-write.py` 设置：
   - `workflowStatus = "archived"`
   - `activePlanRef = null`
   - `activeTaskId = null`
   - `nextAction = "开启下一个 workflow"`
5. 再次运行 `lint-harness.py` 与 `validate-state.py`。

归档完成后，archived plan package 内的 `plan.md`、`tasks.json`、`handoff.md`、`closure.md` 共同组成可审计记录；运行态真相源仍是 `work/workflow-state.json`。
