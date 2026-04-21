# workflow-state.json 规则

1. `workflow-state.json` 只保存当前工作流的运行态，不保存任务列表，不保存历史流水。
2. `activePlanRef` 只是当前 plan 的引用路径，不要把 plan 内容写进本文件。
3. `activeTaskId` 表示当前唯一激活的任务；如果当前还没有进入任务执行阶段，则填 `null`。
4. `workflowStatus` 表示工作流整体状态，不表示某个 task 的状态。
5. `currentPhase` 表示当前阶段，例如 `planning`、`implementing`、`testing`。
6. `nextAction` 必须是“当前唯一可执行的一步”，不能写成多步计划，不能写成高层目标。
7. `nextAction` 必须和 `currentPhase`、`activeTaskId` 保持一致。
8. 如果当前还在产出 plan 或拆解 tasks，则：
   - `currentPhase` 应为 `planning`
   - `activeTaskId` 应为 `null`
9. 新任务必须加入 `tasks.json`，不要追加到 `workflow-state.json`。
10. `workflow-state.json` 是运行态主入口，`handoff.md` 中的 nextAction 应从这里派生，而不是独立发明。