# tasks.json 与 Workflow Gate 的边界

## 结论

`tasks.json` 是执行真相源，但 testing 和 review 本身不应建模为独立 task。它们属于 workflow 阶段 / gate，用来判断当前 task 能否进入 `done`，以及整个 plan 能否继续推进或归档。

也就是说：

- task 描述一个可交付工作单元。
- testing / review 是工作单元完成前必须经过的流程闸门。
- testing / review 的结构化结果需要回写到当前 task，作为完成证据。

---

## tasks.json 的生命周期

### 1. 抽取

`tasks.json` 应从审阅通过后的 `plan.md` 抽取，而不是由 Agent 从自由文本中临时猜测。

推荐流程：

1. Agent 使用 `plan-writing` skill 生成 `plan.md` 草案。
2. 用户或协作者审阅 `plan.md`。
3. `plan.md` 通过审阅后，Agent 调用脚本从结构化任务区块抽取 `tasks.json`。
4. 脚本用 `.harness/schemas/tasks.schema.json` 校验生成结果。

关键边界：

- Agent 决定任务如何拆分。
- 脚本只解析、落盘、校验。
- 脚本不判断需求范围，不猜测任务语义。

### 2. 落盘

`tasks.json` 应落盘到当前 active plan 目录：

```text
work/plans/active/<PLAN-ID>/tasks.json
```

初始状态应保持保守：

- `status = "idle"`
- `currentStep = ""`
- `nextAction = ""`
- `verification.lastResult = "not_run"`
- `review.lastResult = "not_run"`

### 3. 更新

执行过程中，Agent 不应直接手写任意状态变更。推荐由模型判断后调用脚本回写：

```text
Agent 判断当前真实状态
  ↓
生成结构化更新意图
  ↓
调用 tasks 写入脚本
  ↓
脚本校验 tasks.schema.json
  ↓
原子写回 tasks.json
```

脚本负责确定性工作：

- 校验 `taskId` 是否存在。
- 校验状态枚举。
- 校验 `dependsOn` 指向合法 task。
- 校验 `done` 前置条件。
- 原子写文件。

Agent 负责语义判断：

- 当前 task 是否真的完成实现。
- 测试失败是否需要回到 implementing。
- review findings 是否阻断。
- 验证结果摘要是否足够准确。

---

## testing / review 是 workflow gate

`workflow-state.currentPhase` 控制当前 workflow 阶段，`workflow-state.ownerRole` 控制当前 gate 的责任角色：

```text
implementing → testing → reviewing → archiving
```

其中 testing 和 review 不是任务，而是 gate：

- testing gate 检查当前 task 是否通过验证。
- review gate 检查当前 task 是否满足 plan acceptance、工程边界和质量要求。
- L0/L1 没有 `tasks.json` 时，也必须通过 `workflow-state.ownerRole` 表达 testing / review 当前由谁推进。

task 不应拆成：

```text
TASK-001 Implement feature
TASK-002 Test feature
TASK-003 Review feature
```

而应建模为：

```text
TASK-001 Implement feature
```

然后在该 task 内记录 gate 结果。

---

## testing 结果如何回写

`verification` 记录测试 / 验证结果：

```json
{
  "verification": {
    "commands": [
      "python3 -m json.tool .harness/templates/tasks.template.json"
    ],
    "checks": [
      "tasks.template.json contains taskId and planSection"
    ],
    "lastResult": "passed"
  }
}
```

规则：

- 自动化测试优先写入 `commands`。
- 无法自动化时，必须写入可复核的 `checks`。
- 不接受只写“手测通过”。
- 测试失败时，`lastResult = "failed"`，workflow 不得进入 reviewing。

---

## review 结果如何回写

`tasks.json` 已引入 `review` block，用来记录 code review gate 的结构化结果：

```json
{
  "review": {
    "score": 90,
    "threshold": 85,
    "lastResult": "passed",
    "rubricVersion": "review-rubric-v1",
    "checks": [
      "implementation matches plan acceptance",
      "no direct write to workflow-state.json outside state-write.py",
      "tests cover the changed behavior"
    ],
    "findings": [
      {
        "severity": "important",
        "blocking": false,
        "summary": "Follow-up is acceptable outside this task",
        "deferReason": "Tracked in handoff"
      }
    ],
    "reportRef": "work/sessions/2026-04-27/session-review.md"
  }
}
```

规则：

- `review.score` 是 0-100 的质量评分；v1 `threshold` 固定为 `85`。
- `review.lastResult = "passed"` 要求 `score >= threshold`、存在 `review.checks`、没有 critical finding、没有 blocking important finding。
- `review.checks` 记录本次 review 的检查维度。
- `review.findings` 只记录摘要，不放大段 review 全文。
- critical finding 一票否决；important finding 默认阻断，若不阻断必须 `blocking = false` 并写明 `deferReason`。
- minor finding 只能是非阻断清理项，必须使用 `blocking = false`。
- `review.lastResult = "failed"` 时，workflow 应回到 implementing。
- 非阻断问题可进入 backlog 或 handoff，不应伪装成 passed。

详细 review 过程可以写入：

- `handoff.md`
- `work/sessions/YYYY-MM-DD/session-<id>.md`
- `closure.md`

不应塞入 `tasks.json`。

---

## task done 的完成条件

当前 task 进入 `done` 的建议前置条件：

1. `acceptance` 已满足。
2. `verification.lastResult == "passed"`。
3. `review.lastResult == "passed"`，`review.score >= review.threshold`，且无 critical / blocking important finding。
4. 所有 `dependsOn` 中的任务均为 `done`。

这意味着 `done` 不是 Agent 的口头声明，而是由 workflow gate 结果支撑的结构化状态。

---

## 一句话边界

`plan.md` 保存任务契约，`tasks.json` 保存执行状态和 gate 结果，workflow 控制 testing/review 阶段，脚本负责将模型判断后的结构化结果安全写回。
