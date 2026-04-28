# archive-rules.md

L2/L3 plan 归档规则。归档是 plan-backed lifecycle 的最后收口动作：把已完成的 active plan package 从 `work/plans/active/<PLAN-ID>/` 迁移到 `work/plans/archived/<PLAN-ID>/`，并将 `workflow-state.json` 收到 archived 形态。

L0/L1 没有 active plan package，不能使用 `archive-plan.py`。L0/L1 的收口动作是 workflow completion：通过 `complete-workflow.py` 校验 direct workflow 形态、记录 session 审计证据，并经 `state-write.py` 将 `workflowStatus` 置为 `completed`。

## 边界

- `closure.md` 是 LLM 负责的语义收口，不由脚本自动生成完整正文。
- `archive-plan.py` 只做确定性校验、目录迁移和 state patch。
- `workflow-state.json` 仍只能经 `state-write.py` 写入；terminal close 必须由 `complete-workflow.py` 或 `archive-plan.py` 调用 `state-write.py --allow-terminal-close` 完成。
- `tasks.json` 在归档阶段不再修改；所有 task 必须已经是 `done`。
- 进入 `archiving` 后，必须先对刚完成的 task 运行 `commit-task.py --task <TASK-ID>`，再编写 `closure.md` 和执行 `archive-plan.py`；task 完成提交与归档提交是两个不同边界。
- `archive-plan.py` 必须在 Git 顶层目录运行，并在归档前确认 worktree 中除 `work/plans/active/<PLAN-ID>/closure.md` 外没有未提交变化；若还有代码、`tasks.json`、`workflow-state.json`、`handoff.md` 或 session evidence 未提交，说明 task completion commit gate 未闭环，必须阻断。
- L0/L1 completion 不迁移目录、不生成 `closure.md`，但必须提供 verification evidence 与 review summary。

## 归档前置条件

归档脚本必须阻断以下情况：

- `workflow-state.currentPhase != "archiving"`。
- `workflow-state.ownerRole != "developer"`。
- `workflow-state.activeTaskId != null`。
- `workflow-state.activePlanRef` 不指向目标 active plan 的 `plan.md`。
- active plan package 缺少 `plan.md`、`tasks.json`、`handoff.md` 或 `closure.md`。
- `closure.md` 缺少 `Delivered`、`Verification Evidence`、`Review Summary`、`Architecture Impact`、`Deviations`、`Follow-ups` 中任一章节。
- `tasks.json` 中存在非 `done` task。
- 归档前存在非当前 plan `closure.md` 的未提交变化，或当前目录不是 Git 顶层。
- `work/plans/archived/<PLAN-ID>/` 已存在。

## 归档动作

最后一个 task 完成后的标准动作：

1. `lifecycle-transaction.py review-passed` 将当前 task 置为 `done`，并把 workflow 置为 `currentPhase=archiving`。
2. 立即运行 `commit-task.py --task <TASK-ID>`，提交该 task 的交付内容、done 状态、handoff 记录与 archiving state。
3. Agent 写入 `closure.md`，其中 `Architecture Impact` 必须记录 root `ARCHITECTURE.md` 与 Harness framework architecture 是否已更新或为何无需更新。
4. 运行 `archive-plan.py PLAN-001`。

`archive-plan.py PLAN-001` 的标准动作：

1. 运行 `lint-harness.py` 与 `validate-state.py`。
2. 校验归档前置条件。
3. 将 `work/plans/active/PLAN-001/` 迁移到 `work/plans/archived/PLAN-001/`。
4. 通过 `state-write.py --allow-terminal-close` 设置：
   - `workflowStatus = "archived"`
   - `activePlanRef = null`
   - `activeTaskId = null`
   - `nextAction = "开启下一个 workflow"`
5. 再次运行 `lint-harness.py` 与 `validate-state.py`。

归档完成后，archived plan package 内的 `plan.md`、`tasks.json`、`handoff.md`、`closure.md` 共同组成可审计记录；运行态真相源仍是 `work/workflow-state.json`。

`workflowStatus = "archived"` 是终态。再次进入 `active` 必须通过 `start-workflow.py` / `state-write.py --allow-terminal-reset` 创建新的 `workflowId`；禁止仅用局部 `workflowStatus` patch 重新打开旧 workflow。

## L0/L1 completion 动作

`complete-workflow.py` 的标准动作：

1. 要求 `workflow-state.activePlanRef = null` 且 `workflow-state.activeTaskId = null`。
2. 要求 `work/plans/active/` 不存在 active plan 目录。
3. 要求当前 direct workflow 处于 `currentPhase=reviewing`、`ownerRole=reviewer`，表示 testing/review gate 已走到最终评审。
4. 要求调用方提供至少一条 verification command 或 check，并提供 review summary 与 architecture impact summary。
5. 预检 `work/sessions/YYYY-MM-DD/workflow-completions.jsonl` 可写。
6. 运行 `lint-harness.py` 与 `validate-state.py`。
7. 通过 `state-write.py --allow-terminal-close` 设置：
   - `workflowStatus = "completed"`
   - `activePlanRef = null`
   - `activeTaskId = null`
   - `nextAction = "开启下一个 workflow"`
8. 将 completion evidence、review summary 与 architecture impact summary 以原子替换方式追加到 `work/sessions/YYYY-MM-DD/workflow-completions.jsonl`。
9. 再次运行 `lint-harness.py` 与 `validate-state.py`。

`workflowStatus = "completed"` 是 direct workflow 终态。再次进入 `active` 必须通过 `start-workflow.py` / `state-write.py --allow-terminal-reset` 创建新的 `workflowId`；禁止仅用局部 `workflowStatus` patch 继续旧 workflow。
