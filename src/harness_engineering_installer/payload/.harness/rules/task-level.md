# task-level.md

任务等级按执行控制复杂度划分，而不是按业务名称或文件改动数量划分。

| 等级 | 名称 | 判定标准 | Plan 形态 |
|---|---|---|---|
| L0 | direct-patch | 局部、低风险、无需正式规划的直接修补任务，但仍需最小确定性验证。 | 不创建 plan；`activePlanRef = null`，`activeTaskId = null`。 |
| L1 | verified-fix | 范围有限的修复任务，必须通过定向测试或可重复验证来确认修复成立。 | 不创建 plan；`activePlanRef = null`，`activeTaskId = null`。 |
| L2 | planned-task | 需要先规划再执行的任务，必须明确完成条件、验证方案和可恢复状态，且执行时保持单 active task。 | 必须有 active plan package。 |
| L3 | decomposed-epic | 无法在单一任务中稳定收敛、必须拆分为多个子任务或阶段性 plan 顺序推进的复杂工作。 | 必须有 active plan package；必要时拆为连续 plan。 |

## 边界规则

- task level 是 workflow 形态的入口判断，不替代 `.harness/rules/workflow-lifecycle.md` 的状态流转规则。
- L0/L1 仍需验证和 review gate，但不创建 `work/plans/active/<PLAN-ID>/`。
- L2/L3 的 planning、implementing、testing、reviewing、archiving 必须通过 active plan package、`tasks.json` 和 workflow state 对齐。
- testing、review、handoff、commit 和 architecture impact 是 gate 或审计动作，不因任务等级升高而建模成独立 task。

