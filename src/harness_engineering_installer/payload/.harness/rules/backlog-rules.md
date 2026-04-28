# backlog-rules.md

Backlog intake 用于在当前 workflow 仍然活跃时记录新进入的工作。它属于 intake-side 子系统，不是执行调度器。`backlogs.json` 只保存尚未被 workflow 或 plan 接管的 pending items；已接管的 item 必须经消费网关移除，并写入消费审计日志。

## 1. 真相源

- pending 队列契约：`.harness/schemas/backlogs.schema.json`
- consumption event 契约：`.harness/schemas/backlog-consumption-event.schema.json`
- 初始模板：`.harness/templates/backlogs.template.json`
- pending 队列：`work/backlog/backlogs.json`
- 消费审计日志：`work/backlog/consumed.jsonl`
- 追加网关：`.harness/scripts/backlog-intake.py`
- 消费网关：`.harness/scripts/backlog-consume.py`

`.harness/` 只保存 schema、template、rule、script 和 tests。backlog 运行态数据只属于 `work/backlog/`。

## 2. Dispatch 语义

`dispatch` 是请求信号，不是执行指令：

- `queue`：记录为普通后续工作，等待当前 active workflow 完成后再评估。
- `preempt`：请求 LLM 评估是否需要中断当前 active workflow。

两者都不得修改 `workflow-state.json`、`tasks.json`、active plan 文件或 `handoff.md`。`preempt` 不会自动激活任务；它只提高语义评估优先级。

## 3. 网关边界

`backlog-intake.py` 是 `work/backlog/backlogs.json` 的唯一确定性追加网关。

脚本必须：

- 在 store 缺失时，从 `.harness/templates/backlogs.template.json` 创建 `work/backlog/backlogs.json`。
- 按 `nextId` 分配下一个 `BL-NNN`，并递增 `nextId`。
- 对缺少 `nextId` 的旧 store 执行确定性迁移：`nextId = max(existing BL-NNN) + 1`。
- 追加前校验现有 store，写入前校验完整的新 store。
- 只对 `work/backlog/backlogs.json` 做原子写入。

`backlog-consume.py` 是 pending item 的唯一确定性消费网关。

脚本必须：

- 校验现有 `backlogs.json`。
- 校验目标 item 存在。
- 校验 `targetRef` 为 `plan:<PLAN-ID>` 或 `workflow:<workflowId>`。
- 对 `plan:<PLAN-ID>`，确认 active plan package 存在 `plan.md`、`tasks.json`、`handoff.md`，`Plan Review Gate` 为 passed，`tasks.json` 合法，且 plan 或 handoff 引用了 backlog id 或 `sourceRef`。
- 对 `workflow:<workflowId>`，确认 `workflow-state.json` 校验通过、workflowId 匹配、active refs 为空，且 session audit 引用了 backlog id 或 `sourceRef`。
- 写入 schema-valid `work/backlog/consumed.jsonl` 事件，事件中保留完整原 item。
- 从 `backlogs.json.items` 删除被消费 item，保留 `nextId`。
- 若 consumed event 已写入但 `backlogs.json` 写回失败，必须回滚刚写入的 consumed event；禁止同一 item 同时保留在 pending queue 与 consumed audit 中。

两个 backlog 脚本都不得：

- 修改 `work/workflow-state.json`。
- 修改任何 `work/plans/active/<PLAN-ID>/tasks.json`。
- 创建、激活、暂停或归档 plan。
- 修改 active plan 文件或 `handoff.md`。
- 将 testing 或 review 建模为 backlog task。

## 4. LLM 边界

是否让 `preempt` item 影响当前 workflow，是 LLM 的语义判断；该判断必须继续走正常 Harness lifecycle 规则和写入网关。intake 脚本只记录可审计输入。
