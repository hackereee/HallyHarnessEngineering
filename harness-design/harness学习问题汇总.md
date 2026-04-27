# Harness 学习问题汇总结论

这些问题已经在当前 Harness Engineering 契约中收敛，结论如下。

## workflow-state.json 是否是唯一工作来源？

是 workflow 级运行态真相源。每次会话开始都必须检查 `work/workflow-state.json`，并用 `.harness/scripts/validate-state.py` 和 `.harness/scripts/lint-harness.py` 校验当前形态。

边界：`workflow-state.json` 不是 task 列表，也不是历史流水。L2/L3 的 task 级状态以 active plan package 内的 `tasks.json` 为准。

## workflow-state.json 能否有多个工作流状态？

不能。`work/workflow-state.json` 同一时刻只承载一个当前 workflow。一个 workflow 完成后必须进入 `completed` 或 `archived`，再开启下一个 workflow。

## Agent 是否需要任务队列文档自动领取任务？

不需要用队列文档驱动当前 active workflow。

- L2/L3 的后续 task 选择来自当前 active plan 的 `tasks.json`，由 `.harness/scripts/select-next-task.py` 只读选择候选。
- 新插入工作进入 `work/backlog/backlogs.json`，只能通过 `.harness/scripts/backlog-intake.py` 追加。
- backlog 的 `preempt` 只请求 LLM 判断是否插队，不自动修改 `workflow-state.json`，也不绕过当前 workflow gate。

优先级：当前 active workflow 以 `workflow-state.json` + active plan `tasks.json` 为准；backlog 只是 intake-side 运行态，不是当前执行真相源。

## 架构变更时是否需要更新 architecture.md？

需要。凡改变 `.harness/` 分层、schema 字段、脚本网关职责、运行态路径或生命周期不变量，都必须同步检查：

- `.harness/ARCHITECTURE.md`
- `.harness/rules/*.md`
- `.harness/schemas/*.json`
- `.harness/templates/*`
- `.harness/scripts/*`
- `.harness/tests/test_*.py`

能用 schema 或脚本表达的约束不要只写在文档里；文档只补充 schema 无法表达的语义。
