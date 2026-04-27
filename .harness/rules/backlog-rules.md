# backlog-rules.md

Backlog intake 用于在当前 workflow 仍然活跃时记录新进入的工作。它属于 intake-side 子系统，不是执行调度器。

## 1. 真相源

- 契约：`.harness/schemas/backlogs.schema.json`
- 初始模板：`.harness/templates/backlogs.template.json`
- 运行态数据：`work/backlog/backlogs.json`
- 写入网关：`.harness/scripts/backlog-intake.py`

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
- 按现有合法 ID 分配下一个 `BL-NNN`。
- 追加前校验现有 store，写入前校验完整的新 store。
- 只对 `work/backlog/backlogs.json` 做原子写入。

脚本不得：

- 修改 `work/workflow-state.json`。
- 修改任何 `work/plans/active/<PLAN-ID>/tasks.json`。
- 创建、激活、暂停或归档 plan。
- 将 testing 或 review 建模为 backlog task。

## 4. LLM 边界

是否让 `preempt` item 影响当前 workflow，是 LLM 的语义判断；该判断必须继续走正常 Harness lifecycle 规则和写入网关。intake 脚本只记录可审计输入。
