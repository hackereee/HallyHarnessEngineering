# plan-writing skill 编写草案

## 设计结论

`plan-writing` 是一个 Harness-native、repo-local skill。它服务于当前 `.harness/` 工件体系，用来指导 Agent 将需求、backlog item 或已确认设计转化为可执行、可恢复、可校验的 active plan package。

初版目标是**简洁高效**，避免把计划流程做成新的阻塞系统：

- 保留 Superpowers `writing-plans` 的计划质量门槛。
- 借鉴 `brainstorming` 的澄清与反思逻辑。
- 取消落盘后的 Plan Review Gate。
- 将不确定点放在落盘前确认。
- 一次性落盘完整 package。
- 将 task activation 归入 `workflow-lifecycle.md`，不放在 `plan-writing` skill 中。

核心流程：

```text
Pre-write Confirmation
  -> Atomic Materialization
  -> Post-write Validation
  -> workflow-lifecycle handles Task Activation
```

目标产物：

```text
work/plans/active/<PLAN-ID>/
├─ plan.md
├─ tasks.json
└─ handoff.md
```

---

## 职责边界

### plan-writing 负责

- 读取 Harness 上下文。
- 判断任务等级 L0/L1/L2/L3。
- 只确认阻塞性不确定点。
- 生成落盘前摘要。
- 做 plan self-review。
- 一次性落盘 `plan.md`、`tasks.json`、`handoff.md`。
- 校验 `tasks.json` schema。
- 校验 `planSection` anchor、`taskId`、`dependsOn`。
- 提示下一步交由 workflow lifecycle 激活 task。

### plan-writing 不负责

- 不执行现有 task。
- 不激活第一个 task。
- 不切换 `activeTaskId`。
- 不推进 testing / reviewing / archiving。
- 不定义 task done 规则。
- 不直接写 `workflow-state.json`。
- 不把 testing / review 建模成独立 task。

### workflow-lifecycle 负责

- Task Activation。
- 第一个 task 如何从 `idle` 进入 `implementing`。
- 当前 task 完成后如何选择并激活下一个 task。
- 无下一个 task 时如何进入 `archiving`。
- testing / reviewing / done / blocked 的阶段转换与前置条件。
- 所有 `workflow-state.json` 变更均经 `state-write.py`。

---

## 建议最终位置

正式 skill 建议落到：

```text
.harness/skills/plan-writing/SKILL.md
```

当前初版应依赖这些已存在或必须读取的 Harness 工件：

```text
harness-design/architecture.md
harness-design/task-level.md
.harness/rules/workflow-lifecycle.md
.harness/schemas/tasks.schema.json
.harness/templates/plan.template.md
.harness/templates/tasks.template.json
.harness/templates/handoff.template.md
.harness/scripts/materialize-tasks.py
.harness/scripts/update-task.py
```

可选或后续补齐的工件：

```text
.harness/scripts/select-next-task.py
```

`materialize-tasks.py` 已是初版核心脚本，plan-writing 应使用它从 `plan.md` 生成并校验 `tasks.json`。`update-task.py` 属于 lifecycle 阶段的 task 状态写入网关，不属于 plan-writing 激活流程。其他尚未存在的 lifecycle 脚本不得写成 plan-writing 的硬依赖。

如果未来要跨仓库复用，应先抽象这些依赖契约，再迁移为可安装通用 skill。

---

## 触发条件

建议 frontmatter：

```yaml
---
name: plan-writing
description: Use when turning a requirement, backlog item, or approved design into Harness L2/L3 plan artifacts, or revising/materializing an approved Harness plan in a repository with .harness.
---
```

description 只描述触发条件，不描述完整流程。原因是 Agent 可能只读 description 就自作主张，跳过 `SKILL.md` 正文。

应触发的场景：

- 用户要求将需求写成 Harness plan。
- backlog item 晋升为 L2/L3 plan。
- 已确认设计需要生成 `work/plans/active/<PLAN-ID>/` package。
- 修改 Harness plan 后需要同步 `tasks.json`。
- 已有 plan contract 需要 materialize 为 `tasks.json` / `handoff.md`。

不应触发的场景：

- L0/L1 直接修复，无需正式 plan。
- 只是在解释 Harness 架构。
- 只是在执行现有 `tasks.json` 中的 task。
- 只是在激活下一个 task。
- 只是在归档已完成 plan。

---

## 借鉴 Superpowers writing-plans 的部分

Superpowers `writing-plans` 的价值在于计划质量控制，而不是文件格式或执行流程。

应借鉴：

1. **面向零上下文执行者**
   - `plan.md` 必须让下一个 Agent 理解目标、范围、文件边界、任务拆分和验证策略。
   - 不依赖当前对话记忆。

2. **scope check**
   - 如果需求覆盖多个独立子系统，应拆成 L3 多阶段 plan。
   - 一个 active plan 必须能产生可独立验证的工作成果。

3. **先列文件边界，再拆任务**
   - 先明确需要创建、修改、验证的文件。
   - 任务拆分围绕文件边界和交付边界，而不是围绕聊天中的自然段落。

4. **bite-sized task**
   - 每个 task 应能在一个受控上下文中完成。
   - task 必须可恢复、可验证、依赖明确。

5. **每个 task 必须可验证**
   - 每个 task 需要 acceptance。
   - 每个 task 需要 verification commands 或 checks。
   - 不允许“完成实现”“完善逻辑”这种无法验证的任务。

6. **禁止占位符**
   - 禁止 `TBD`、`TODO`、`后续完善`、`添加适当错误处理`。
   - 禁止无路径的“相关脚本”“相关文档”。

7. **self-review**
   - 覆盖率：需求是否都有对应任务。
   - 占位符：是否存在空泛语句。
   - 命名一致性：taskId、planSection、文件路径是否一致。
   - 验证完整性：每个 task 是否有 acceptance 与 verification。

不应照搬：

- 不在 `plan.md` 使用 checkbox 跟踪执行状态。
- 不把 `currentStep` / `nextAction` / `lastResult` 写入 `plan.md`。
- 不要求在 `plan.md` 中写完整代码 patch。
- 不把 commit 命令作为 plan 主体。
- 不让 `plan.md` 变成执行日志。
- 不引入落盘后的人工 Plan Review Gate。

---

## 借鉴 brainstorming 的部分

`brainstorming` 的价值在于降低歧义，而不是制造完整 spec 流程。

应借鉴：

- 先理解当前 Harness 上下文。
- 只询问真正阻塞落盘的问题。
- 一次只问一个问题。
- 如果存在多个真实方案，给出 trade-off 和推荐方案。
- 信息足够后给落盘前摘要。
- 落盘前检查 placeholder、前后矛盾、范围过大、歧义。

不应照搬：

- 不要求额外写设计 spec。
- 不要求 commit 设计文档。
- 不要求逐段 review。
- 不要求用户确认每一个 task。

原则：

```text
Confirm uncertainty, not everything.
```

确定项直接纳入落盘前摘要；只有阻塞性不确定点才提问。

---

## Harness-native 边界

### plan.md 的边界

`plan.md` 是规划真相源，应采用“任务契约型”边界，而不是“大纲型”或“执行手册型”。

必须包含：

- 背景与目标。
- 范围与非范围。
- 架构 / 实现方向。
- 文件边界。
- 任务拆分依据。
- 任务契约区块。
- 验证策略。
- 风险与开放问题。

任务契约区块应包含：

- `taskId`
- 稳定 anchor
- 标题
- 目标
- 文件边界
- 依赖关系
- acceptance
- verification commands / checks

不应包含：

- checkbox 进度。
- 当前执行状态。
- 当前下一步。
- 最近测试结果。
- review 结果。
- 大段执行日志。
- 大段完整代码 patch。

示例任务契约：

```md
<a id="task-001-define-tasks-schema"></a>

### TASK-001: Define tasks schema

Goal: Define the machine-checkable schema for plan tasks.

Files:
- Create: `.harness/schemas/tasks.schema.json`
- Create: `.harness/templates/tasks.template.json`
- Modify: `.harness/rules/workflow-lifecycle.md`

Depends on: []

Acceptance:
- `tasks.schema.json` validates `tasks.template.json`.
- Task IDs use `TASK-001` style identifiers.
- `planSection` points to a stable anchor in `plan.md`.

Verification:
- Run: `python3 -m json.tool .harness/schemas/tasks.schema.json`
- Check: `tasks.template.json` uses `taskId`, `planSection`, and `dependsOn`.
```

### tasks.json 的边界

`tasks.json` 是执行真相源。它从 `plan.md` 的任务契约区块抽取，不由 Agent 临时猜测。

必须由 `.harness/schemas/tasks.schema.json` 校验。

当前基础结构：

```json
{
  "$schema": "../../../../.harness/schemas/tasks.schema.json",
  "planId": "PLAN-001",
  "planRef": "./plan.md",
  "tasks": [
    {
      "taskId": "TASK-001",
      "title": "Define tasks schema",
      "planSection": "task-001-define-tasks-schema",
      "status": "idle",
      "currentStep": "",
      "nextAction": "",
      "ownerRole": "developer",
      "dependsOn": [],
      "files": {
        "create": [],
        "modify": [],
        "test": []
      },
      "acceptance": [],
      "verification": {
        "commands": [],
        "checks": [],
        "lastResult": "not_run"
      },
      "blockedReason": ""
    }
  ]
}
```

说明：

- 从 `work/plans/active/<PLAN-ID>/tasks.json` 指向 `.harness/schemas/tasks.schema.json` 的相对路径是 `../../../../.harness/schemas/tasks.schema.json`。
- 初始 task 均为 `idle`。
- 初始 `ownerRole` 为 `developer`，表示 materialization 后的下一接手角色。
- active task 流转时，`status` 与 `ownerRole` 必须匹配：`implementing/developer`、`testing/tester`、`reviewing/reviewer`。
- `workflow-state.ownerRole` 是 workflow gate 责任角色；L2/L3 有 active task 时必须与当前 task `ownerRole` 对齐。
- `currentStep`、`nextAction`、`verification.lastResult` 使用 schema 允许的初始值。
- 当前 schema 支持 `reviewing` task status，但未定义 `review` block，初版不得生成 `review` 字段。
- 若后续引入 code review gate，应先更新 schema、template、lifecycle，再更新 skill。
- 任务契约区块应放在 `plan.md` 末尾；当前 `materialize-tasks.py` 会读取 task body 直到下一个 task anchor，契约区块后不应再追加普通章节。

### handoff.md 的边界

`handoff.md` 是恢复入口，不是状态真相源。它应摘要说明：

- 当前 plan 来源。
- 落盘前确认结论。
- 初始 task 激活建议。
- pre-activation 状态：`activeTaskId = null`、`currentPhase = planning`、`ownerRole = planner`、task 均为 `idle`。
- Role Handoff：`fromRole`、`toRole`、交接原因、状态真相源。
- 风险与开放问题。
- 下一步原子动作。

`handoff.md` 可以记录角色交接摘要，但不是真相源。状态仍以 `workflow-state.json` 与 `tasks.json` 为准。详细测试输出、review 过程、执行流水应写入 `work/sessions/...` 或归档时的 `closure.md`，不堆进 `handoff.md`。

---

## 初版核心流程

### 阶段 1：Pre-write Confirmation

目标：在落盘前消除会导致 plan package 失真的阻塞性不确定点。

步骤：

1. 读取 Harness 上下文：
   - `harness-design/architecture.md`
   - `harness-design/task-level.md`
   - `.harness/rules/workflow-lifecycle.md`
   - `.harness/schemas/tasks.schema.json`
   - `.harness/templates/tasks.template.json`

2. 判断任务等级：
   - L0/L1：不创建 plan，交给直接执行流程。
   - L2：创建单个 active plan package。
   - L3：默认拆成顺序 phase plans；如果能放进一个 active plan 且可独立验证，则按 L2 处理。

3. 识别阻塞性不确定点：
   - scope / non-scope 不清。
   - 文件边界不清。
   - task 依赖关系不清。
   - acceptance / verification 不可验证。
   - L2/L3 分类无法判断。

4. 只对阻塞性问题逐一提问。

5. 信息足够后输出落盘前摘要：
   - planId 与 plan 路径。
   - 任务等级。
   - scope / non-scope。
   - 文件边界。
   - task 列表、依赖、acceptance、verification。
   - 风险与开放问题。
   - 明确说明下一步将一次性落盘完整 package。

6. 用户确认摘要后进入落盘。

硬规则：

```text
Do not write a partial active plan package.
Do not create plan.md alone under work/plans/active/<PLAN-ID>/.
```

### 阶段 2：Atomic Materialization

目标：一次性生成完整 active plan package。

步骤：

1. 创建 `work/plans/active/<PLAN-ID>/`。
2. 写入 `plan.md`。
3. 调用 `.harness/scripts/materialize-tasks.py` 从 `plan.md` 的任务契约区块生成 `tasks.json`。
4. 写入 `handoff.md`。
5. 初始 task 全部保持 `status = "idle"`。
6. 不设置 `activeTaskId`。
7. 不把任何 task 改为 `implementing`。
8. 不推进 `workflow-state.currentPhase` 到 `implementing`。

`plan-writing` 可以准备 activation 建议，但不得执行 activation：

```text
Suggested next lifecycle action:
Activate the first eligible idle task according to workflow-lifecycle.md.
```

### 阶段 3：Post-write Validation

目标：证明落盘 package 可被 Harness 接管。

必须检查：

- `tasks.json` 是合法 JSON。
- `tasks.json` 通过 `.harness/schemas/tasks.schema.json`。
- 每个 `taskId` 唯一。
- 每个 `planSection` 对应 `plan.md` 中存在的稳定 anchor。
- 每个 `dependsOn` 指向存在的 task。
- 每个 task 有文件边界。
- 每个 task 有 acceptance。
- 每个 task 有 verification commands 或 checks。
- `handoff.md` 只做恢复摘要，不替代 state。

`materialize-tasks.py` 已覆盖 `tasks.json` 的 JSON、schema、taskId、anchor、dependsOn、文件边界、acceptance 与 verification 校验。plan-writing 仍需额外检查 `handoff.md` 边界，以及没有执行 task activation。

---

## Task Activation 的归属

Activation 是 lifecycle 动作，不是 plan-writing 动作。

建议在 `workflow-lifecycle.md` 中定义：

```text
planning -> implementing
  条件：
  - plan.md + tasks.json + handoff.md 已落盘
  - tasks.json schema 通过
  - 选中第一个 dependsOn 已满足的 idle task
  - 将该 task 标记为 implementing/developer
  - state.activeTaskId = taskId
  - state.currentPhase = implementing
  - state.ownerRole = developer
  - state.nextAction 指向该 task 的第一步原子动作
```

当前 task 进入 testing / reviewing：

```text
implementing -> testing
  - state.currentPhase = testing
  - state.ownerRole = tester
  - 当前 task 标记为 testing/tester
  - verification.lastResult 保持 not_run 或 failed

testing -> reviewing
  - verification.lastResult == passed
  - state.currentPhase = reviewing
  - state.ownerRole = reviewer
  - 当前 task 标记为 reviewing/reviewer
```

review 未通过时：

```text
reviewing -> implementing
  条件：
  - 当前 task review 未通过
  - state.currentPhase = implementing
  - state.ownerRole = developer
  - 当前 task 标记为 implementing/developer
  - nextAction 指向修复评审发现的原子动作
```

review 通过且还有下一个 task 时：

```text
reviewing -> implementing
  条件：
  - 当前 task 满足 done 前置条件并标记为 done
  - 仍存在可执行的 idle task
  - 选中下一个 task
  - state.currentPhase = implementing
  - state.ownerRole = developer
  - 下一个 task 标记为 implementing/developer
  - activeTaskId 切换到下一个 task
```

如果没有下一个 task：

```text
reviewing -> archiving
  条件：
  - 当前 task done
  - plan 中所有 task 均 done
  - state.activeTaskId = null
  - state.currentPhase = archiving
  - state.ownerRole = developer
```

`select-next-task.py`、`update-task.py` 更适合归入 lifecycle 工具，而不是 plan-writing 私有工具。

---

## testing / review gate

testing 和 review 是 workflow gate，不是独立 task。

不建议建模为：

```text
TASK-001 Implement feature
TASK-002 Test feature
TASK-003 Review feature
```

应建模为：

```text
TASK-001 Implement feature
```

并在该 task 内记录 gate 结果。

当前 schema 支持 `reviewing` status 与 `ownerRole=reviewer`，但只定义了 `verification`，未定义 `review` block。因此初版要求：

- verification commands / checks 在计划阶段定义清楚。
- `verification.lastResult` 初始为 `not_run`。
- testing 阶段由 workflow lifecycle 更新 verification 结果。
- reviewing 阶段由 workflow lifecycle 更新 task `status=reviewing`、`ownerRole=reviewer`。
- review 结论暂写入 handoff/session 摘要；结构化 `review` block 作为后续能力。

review gate 可作为后续能力引入。引入前必须先更新：

- `.harness/schemas/tasks.schema.json`
- `.harness/templates/tasks.template.json`
- `.harness/rules/workflow-lifecycle.md`
- 对应脚本与 skill 文档

---

## 脚本协作模型

skill 负责判断与编排，脚本负责确定性操作。

### materialize-tasks.py（已实现）

当前已提供：

```text
.harness/scripts/materialize-tasks.py
```

职责：

- 输入已确认的 `plan.md`。
- 解析结构化任务契约区块。
- 生成 `tasks.json`。
- 校验 `tasks.schema.json`。
- 校验 taskId 唯一。
- 校验 dependsOn 指向存在 task。
- 校验 planSection anchor 存在。
- 校验每个 task 有文件边界、acceptance、verification。
- 原子写入 `tasks.json`。

不负责：

- 判断需求范围。
- 决定任务如何拆分。
- 猜测自由文本中的任务。
- 判断 verification 是否语义充分。
- 激活 task。

### lifecycle scripts（后续建议）

这些脚本应归入 workflow lifecycle，而不是 plan-writing：

```text
.harness/scripts/select-next-task.py
```

职责：

- 选择下一个可执行 task。
- 输出给 `state-write.py` 使用的 patch。

### state-write.py

`state-write.py` 仍是 `workflow-state.json` 唯一写入网关。plan-writing skill 不直接修改 state 文件；需要 state 变更时只输出建议或 patch，由 lifecycle 流程接管。

---

## 正式 SKILL.md 建议结构

正式 `SKILL.md` 可采用：

```md
---
name: plan-writing
description: Use when turning a requirement, backlog item, or approved design into Harness L2/L3 plan artifacts, or revising/materializing an approved Harness plan in a repository with .harness.
---

# Plan Writing

## Overview
Harness-native skill for producing complete L2/L3 active plan packages.

## When to Use
- Trigger on Harness L2/L3 plan creation, revision, or materialization.
- Do not trigger for L0/L1 direct work, task activation, task execution, or archiving.

## Inputs
- Read Harness lifecycle, task level, tasks schema, and tasks template.
- Use `.harness/scripts/materialize-tasks.py` to generate and validate `tasks.json`.
- Use `.harness/templates/handoff.template.md` for handoff shape.
- Use optional plan templates if present.

## Flow
1. Pre-write Confirmation
2. Atomic Materialization
3. Post-write Validation

## Pre-write Confirmation
- Classify L0/L1/L2/L3.
- Ask only blocking questions.
- Present a concise write summary.
- Continue only after the summary is confirmed.

## Atomic Materialization
- Write `plan.md`, `tasks.json`, and `handoff.md` together.
- Generate `tasks.json` through `.harness/scripts/materialize-tasks.py`.
- Never create a partial active plan package.
- Leave all tasks idle.
- Do not activate the first task.

## Post-write Validation
- Validate JSON and schema.
- Check task IDs, anchors, dependencies, acceptance, verification, and handoff scope.

## Lifecycle Boundary
- Task activation, next-task selection, testing, review, done, and archive belong to `workflow-lifecycle.md`.

## Self-Review Checklist
- Check coverage, scope, placeholders, contradictions, anchors, files, acceptance, verification, and state leakage.

## Common Mistakes
- Creating only `plan.md` under active.
- Asking the user to review every obvious detail.
- Generating schema-invalid fields such as `review` before schema support exists.
- Activating a task from plan-writing.
- Splitting testing or review into separate tasks.
```

第一版可以只保留一个 `SKILL.md`，避免过早拆分。如果正文超过 500 行，再把详细示例移到：

```text
.harness/skills/plan-writing/references/examples.md
```

---

## Self-review checklist

Agent 完成 plan-writing 时必须检查：

- 是否正确判断 L0/L1/L2/L3。
- 是否只有 L2/L3 创建 plan package。
- 是否只确认阻塞性不确定点。
- 是否已给出落盘前摘要并获得确认。
- 是否一次性落盘 `plan.md`、`tasks.json`、`handoff.md`。
- 是否没有创建 partial active plan package。
- `plan.md` 是否无 checkbox 执行状态。
- `plan.md` 是否无 `TBD` / `TODO` / 空泛语句。
- 每个 task 是否有唯一 `taskId`。
- 每个 task 是否有唯一稳定 anchor。
- 每个 `planSection` 是否能回链到 anchor。
- 每个 `dependsOn` 是否指向存在 task。
- 每个 task 是否有文件边界。
- 每个 task 是否有 acceptance。
- 每个 task 是否有 verification。
- `tasks.json` 是否通过 `.harness/schemas/tasks.schema.json`。
- active task 的 `status` / `ownerRole` 是否符合 lifecycle 对照。
- `workflow-state.ownerRole` 是否符合 `currentPhase`，且在 L2/L3 active task 场景下与 task `ownerRole` 对齐。
- 是否没有生成当前 schema 不支持的 `review` 字段。
- `handoff.md` 是否包含 Role Handoff 摘要，且只做恢复摘要、不替代 state。
- 是否没有激活 task。
- 是否没有直接写 `workflow-state.json`。

---

## 压力场景

后续验证 skill 时，建议使用这些场景检查 Agent 是否会犯错：

1. **把 checkbox 写进 plan.md**
   - 期望：skill 阻止，要求执行状态进入 `tasks.json` 或 workflow state。

2. **只写 plan.md，不生成 tasks.json / handoff.md**
   - 期望：阻止；active plan package 必须一次性完整落盘。

3. **用户未要求逐项确认，Agent 仍反复确认每个 task**
   - 期望：阻止；只确认阻塞性不确定点。

4. **从自由文本猜任务**
   - 期望：要求 `plan.md` 中存在结构化任务契约区块。

5. **把 testing/review 拆成独立 task**
   - 期望：阻止，要求作为 workflow gate 记录结果。

6. **没有 verification 的 task**
   - 期望：self-review 失败。

7. **planSection 使用人类标题**
   - 期望：要求稳定 anchor id。

8. **plan-writing 激活第一个 task**
   - 期望：阻止，要求交给 `workflow-lifecycle.md` 的 Task Activation。

9. **生成当前 schema 不支持的 review 字段**
   - 期望：阻止，除非 schema / template / lifecycle 已先升级。

10. **直接写 workflow-state.json**
    - 期望：阻止，要求通过 `state-write.py` 或 lifecycle 流程。

这些压力场景可以作为后续 `writing-skills` 验证的测试用例。
