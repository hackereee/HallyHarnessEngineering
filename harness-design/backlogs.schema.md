# backlogs.schema.md
backlogs.json 注释文档

## 1. 文件结构

`backlog-index.json` 的根对象包含一个字段：

- `items`: backlog 项数组

示例：

```json
{
  "items": [
    {
      "id": "BL-001",
      "title": "修复登录页闪退",
      "summary": "当前 workflow 执行过程中插入的新任务，需要评估是否插队。",
      "dispatch": "preempt",
      "source_ref": "chat:2026-04-21-001",
      "created_at": "2026-04-21T13:00:00+08:00",
      "notes": "疑似生产故障"
    }
  ]
}

```

## 2. 字段说明

### id

- 类型：`string`
- 必填：是
- 格式：`BL-{三位数字}`，如 `BL-001`

说明：backlog 项的唯一标识符，全局不可重复。

### title

- 类型：`string`
- 必填：是

说明：backlog 项的简短标题，用于快速识别任务内容。

### summary

- 类型：`string`
- 必填：是

说明：任务的详细描述，说明任务背景、插入原因及需要关注的事项。

### dispatch

- 类型：`string`
- 必填：是
- 可选值：
  - `queue`
  - `preempt`

说明：
- `queue`：正常排队，等待当前 active workflow 完成后再处理
- `preempt`：优先评估是否插队，不等于立即执行

### source_ref

- 类型：`string`
- 必填：是
- 格式：`{来源类型}:{标识符}`，如 `chat:2026-04-21-001`

说明：任务的来源引用，用于追溯任务最初提出的位置（如对话记录、issue、邮件等）。

### created_at

- 类型：`string`
- 必填：是
- 格式：ISO 8601 日期时间，如 `2026-04-21T13:00:00+08:00`

说明：backlog 项的创建时间，带时区信息。

### notes

- 类型：`string`
- 必填：否

说明：补充备注，用于记录额外上下文或处理建议。