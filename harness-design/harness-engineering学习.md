# Harness Engineering 学习结论：会话启动与未完成 workflow

当 `work/workflow-state.json` 存在未完成 workflow 时，Agent 不应重新猜测上下文，也不应扫描目录后自行选择任务；必须以 `workflow-state.json` 为 workflow 级运行态真相源，并按 `.harness/rules/workflow-lifecycle.md` 继续推进。

## 当前结论

- `workflow-state.json` 只承载一个当前 workflow 的运行态。
- L0/L1 没有 active plan 和 active task，当前责任由 `workflow-state.ownerRole` 表达。
- L2/L3 通过 `activePlanRef` 指向 active plan package；执行、测试、评审阶段必须有且仅有一个 `activeTaskId`。
- `tasks.json` 是 task 级执行真相源；`handoff.md` 只做恢复摘要。
- 如果 state 缺失但存在 active plan，`session-start.py` 必须阻断并交给 Agent 做语义恢复，脚本不猜测当前 workflow。

## 会话启动处理

1. 运行 `.harness/scripts/session-start.py` 或等价 preflight。
2. 校验 `.harness/` 关键工件、当前 `workflow-state.json` 和 active plan package。
3. 按 `workflow-state.nextAction` 执行下一步；如果 nextAction 不原子，先修正 state，再继续。

详细规则见：

- `AGENTS.md`
- `.harness/ARCHITECTURE.md`
- `.harness/rules/workflow-lifecycle.md`
- `learning-notes/tasks-workflow-gates.md`
