# backlogs.schema.md

`backlogs.json` 是 Harness intake-side 运行态数据，正式结构由 `.harness/schemas/backlogs.schema.json` 约束，初始化样例来自 `.harness/templates/backlogs.template.json`。

## 1. 文件位置与职责

- Schema：`.harness/schemas/backlogs.schema.json`
- Template：`.harness/templates/backlogs.template.json`
- Runtime store：`work/backlog/backlogs.json`

`.harness/` 只保存契约和模板，不保存运行态 backlog 数据。`work/backlog/backlogs.json` 只记录 incoming work，不修改 `workflow-state.json`，不激活 plan/task，也不改变当前 workflow phase。

## 2. 根对象

根对象包含：

- `$schema`：必填，模板中为 `../schemas/backlogs.schema.json`。
- `items`：必填，backlog 项数组；初始模板为空数组。

示例：

```json
{
  "$schema": "../schemas/backlogs.schema.json",
  "items": [
    {
      "id": "BL-001",
      "title": "修复登录页闪退",
      "summary": "当前 workflow 执行过程中插入的新任务，需要评估是否插队。",
      "dispatch": "preempt",
      "sourceRef": "chat:2026-04-27-001",
      "createdAt": "2026-04-27T13:00:00+08:00",
      "notes": "疑似生产故障"
    }
  ]
}
```

## 3. Backlog Item 字段

### id

- 类型：`string`
- 必填：是
- 格式：`BL-001`
- 规则：在同一个 `items` 数组内唯一。

说明：backlog item 的审计标识。标准 JSON Schema Draft 2020-12 不能原生表达“数组内某个字段唯一”，因此 schema 声明格式约束，Harness schema 测试和后续写入网关负责执行唯一性校验。

### title

- 类型：`string`
- 必填：是
- 长度：1-120

说明：backlog item 的短标题，用于快速识别 incoming work。

### summary

- 类型：`string`
- 必填：是
- 长度：1-2000

说明：任务背景、触发原因、目标或需要关注的上下文。

### dispatch

- 类型：`string`
- 必填：是
- 可选值：`queue`、`preempt`

说明：

- `queue`：记录为普通后续工作，等待当前 active workflow 自然完成后再评估。
- `preempt`：请求 LLM 评估是否需要中断当前 workflow，但不等于立即执行。

### sourceRef

- 类型：`string`
- 必填：是
- 格式：`{来源类型}:{标识符}`，如 `chat:2026-04-27-001`、`issue:123`

说明：任务来源引用，用于追溯任务最初提出的位置。

### createdAt

- 类型：`string`
- 必填：是
- 格式：ISO 8601 日期时间，必须带时区，如 `2026-04-27T13:00:00+08:00`

说明：backlog item 创建时间，用于审计和排序。

### notes

- 类型：`string`
- 必填：否
- 长度：0-2000

说明：补充备注，不承载状态机语义。
