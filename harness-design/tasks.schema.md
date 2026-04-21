# tasks.schema.md

## 目的

`tasks.template.json` 用于保存当前工作流中的任务列表，是 **agent 与脚本可直接读取的结构化任务文档**。  
它关注的是 **执行状态**，而不是完整的规划说明。

完整背景、边界条件、详细设计应放在 `plan.md` 中。  
`tasks.template.json` 只保留执行阶段真正需要的最小字段。

---

## 设计原则

1. **JSON 保持纯净**
   - 不在 JSON 内添加注释
   - 保证脚本、校验器、agent 都能稳定解析

2. **plan 与 task 分离**
   - `plan.md` 负责完整规划、约束、设计说明
   - `tasks.template.json` 负责任务执行状态

3. **启动优先读取 task**
   - agent 启动时优先读取 `workflow-state.json` 与当前 task
   - 只有在 task 信息不足时，再按 `plan_ref + plan_section` 回读 `plan.md`

4. **单一职责**
   - `tasks.template.json` 不是 plan 的副本
   - 不重复保存大段设计说明
   - 只记录执行阶段真正需要的信息

---

## 顶层结构

```json
{
  "tasks": [
    {
      "id": "task-001",
      "title": "Define workflow-state schema",
      "plan_ref": "./plans/harness-v1/plan.md",
      "plan_section": "Chunk 1 - Workflow State",
      "status": "idle",
      "current_step": "",
      "next_action": "",
      "owner_role": "developer",
      "depends_on": [],
      "verification": {
        "commands": [],
        "checks": [],
        "last_result": "not_run"
      },
      "blocked_reason": ""
    }
  ]
}
```

---

## 字段说明

### `tasks`
- 类型：`array`
- 含义：任务对象列表
- 规则：
  - 每个元素代表一个独立任务
  - 每个任务的 `id` 必须唯一

---

### `id`
- 类型：`string`
- 含义：任务唯一标识
- 建议格式：`task-001`、`task-002`
- 规则：
  - 在同一个 `tasks.template.json` 中必须唯一
  - 不应随意修改，避免依赖关系失效

---

### `title`
- 类型：`string`
- 含义：任务标题
- 要求：
  - 简洁明确
  - 能直接表达任务目标
- 示例：
  - `Define workflow-state schema`
  - `Draft tasks.template.json`

---

### `plan_ref`
- 类型：`string`
- 含义：当前任务对应的 plan 文件路径
- 作用：
  - 当 task 信息不足时，agent 可回到该 plan 查找详细设计
- 示例：
  - `./plans/harness-v1/plan.md`

---

### `plan_section`
- 类型：`string`
- 含义：当前任务在 `plan.md` 中对应的章节、区块或 chunk 名称
- 作用：
  - 帮助 agent 定位到 plan 中的具体部分
- 示例：
  - `Chunk 1 - Workflow State`
  - `Milestone 2 - Task Extraction`

> 说明：  
> 你也可以把该字段命名为 `plan_chunk`。  
> 若强调“章节定位”，推荐使用 `plan_section`；若强调“规划块”，可使用 `plan_chunk`。  
> 第一版建议二选一，不要两个字段同时存在。

---

### `status`
- 类型：`string`
- 含义：任务当前状态
- 建议枚举值：
  - `idle`：尚未开始
  - `implementing`：正在实现
  - `testing`：正在验证或测试
  - `blocked`：被阻塞，无法继续推进
  - `done`：已完成
- 规则：
  - 一个任务同一时刻只能有一个状态
  - 状态应反映当前真实执行阶段

---

### `current_step`
- 类型：`string`
- 含义：当前正在进行的具体步骤
- 作用：
  - 帮助 agent 在会话恢复时快速知道“现在做到哪一步了”
- 示例：
  - `Draft minimal schema fields`
  - `Run validation against example JSON`

> 建议：  
> 该字段应写“当前正在做的动作”，而不是写长期目标。

---

### `next_action`
- 类型：`string`
- 含义：当前步骤之后，下一步最明确、最可执行的动作
- 作用：
  - 作为 agent 恢复后的直接行动入口
- 示例：
  - `Update tasks.template.json with verification fields`
  - `Revise status enum documentation`

> 建议：  
> `next_action` 应尽量具体，避免写成模糊表述，例如“继续处理”“进一步完善”。

---

### `owner_role`
- 类型：`string`
- 含义：当前任务的责任角色
- 第一版建议值：
  - `developer`
- 后续可扩展：
  - `reviewer`
  - `planner`
  - `tester`

> 说明：  
> 由于你当前是最小起步版本，第一版只使用 `developer` 即可。  
> 不必为了未来扩展过早复杂化。

---

### `depends_on`
- 类型：`string[]`
- 含义：当前任务依赖的前置任务 ID 列表
- 规则：
  - 仅填写同一 `tasks.template.json` 中存在的任务 `id`
  - 列表中的所有任务都必须为 `done`，当前任务才可被激活
  - 无前置依赖时写 `[]`
- 示例：

```json
"depends_on": ["task-001", "task-002"]
```

> 注意：  
> `depends_on` 只存 **任务 ID**，不要存：
> - 自然语言描述
> - 文件路径
> - plan section 名称
> - 角色名

---

### `verification`
- 类型：`object`
- 含义：任务的最小验证信息
- 作用：
  - 指定如何检查任务是否真正完成
  - 防止 agent 只“声称完成”，却没有验证依据

#### `verification.commands`
- 类型：`string[]`
- 含义：可执行的验证命令
- 示例：
  - `python scripts/validate_tasks.py`
  - `dotnet test`

#### `verification.checks`
- 类型：`string[]`
- 含义：无需命令也可核对的验证项
- 示例：
  - `Schema example is valid JSON`
  - `All required status values are documented`

#### `verification.last_result`
- 类型：`string`
- 建议枚举值：
  - `not_run`
  - `passed`
  - `failed`

> 第一版建议保持简单：  
> 用 `commands + checks + last_result` 已足够支撑最小可执行验证闭环。

---

### `blocked_reason`
- 类型：`string`
- 含义：当 `status = "blocked"` 时，用于记录阻塞原因
- 示例：
  - `Waiting for finalized workflow-state field list`
  - `Plan section is inconsistent with current schema`

- 规则：
  - 未阻塞时可为空字符串 `""`
  - 若状态为 `blocked`，建议必须填写具体原因

> 建议：  
> `blocked_reason` 应写可操作的阻塞原因，而不是泛泛写“有问题”“待确认”。

---

## 字段关系建议

### `current_step` 与 `next_action`
- `current_step`：现在正在做什么
- `next_action`：下一步马上要做什么

### `depends_on` 与 `plan_ref`
- `depends_on`：执行顺序依赖
- `plan_ref` / `plan_section`：设计信息来源

### `verification` 与 `status`
- `status` 表示任务处于哪个阶段
- `verification` 表示如何判断该任务能否进入 `done`

---

## 最小使用规则

建议 agent 在执行时遵循以下规则：

1. 启动时优先读取：
   - `AGENTS.md`
   - `workflow-state.json`
   - 当前 active task

2. 若 task 信息足够，则直接执行当前任务

3. 若 task 信息不足，再通过：
   - `plan_ref`
   - `plan_section`
   去读取 `plan.md` 对应内容

4. 更新任务时：
   - 先更新 `current_step`
   - 再更新 `next_action`
   - 状态变化时同步更新 `status`
   - 阻塞时填写 `blocked_reason`

5. 只有在验证通过后，任务才应进入 `done`

---

## 第一版简化建议

对于最小可执行 harness，建议先保持以下约束：

- 只允许一个 active task
- `owner_role` 只用 `developer`
- `depends_on` 只支持简单的 task id 列表
- `verification.last_result` 只用 `not_run / passed / failed`
- 不在 `tasks.template.json` 中写长段说明文字

这样可以最大限度降低系统复杂度，同时保留后续扩展空间。

---

## 推荐定位

可以把这份文档理解为：

- `plan.md`：规划真相源
- `tasks.template.json`：执行真相源
- `workflow-state.json`：当前状态入口

这三者分工明确后，agent 的启动、恢复、执行与验证都会更稳定。
