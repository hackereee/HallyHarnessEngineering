# plan-writing skill 编写草案

## 目的

`plan-writing` 是一个 Harness-native、repo-local skill。它服务于当前 `.harness/` 工件体系，用来指导 Agent 将需求、backlog item 或已确认设计转化为可审阅、可执行、可恢复、可校验的 active plan package。

它不是通用的 implementation plan skill，也不是 Superpowers `writing-plans` 的包装。它借鉴 Superpowers 的计划质量门槛，但遵守 Harness 自己的分层：

- `plan.md` 是规划真相源。
- `tasks.json` 是执行真相源。
- `workflow-state.json` 是当前状态入口。
- `handoff.md` 是会话恢复入口。
- schema / template / rules / scripts 是 Harness 的基础设施，不属于 skill 私有资源。

目标产物：

```text
work/plans/active/<PLAN-ID>/
├─ plan.md
├─ tasks.json
└─ handoff.md
```

---

## 建议最终位置

草案成熟后，正式 skill 建议落到：

```text
.harness/skills/plan-writing/SKILL.md
```

该 skill 默认依赖当前仓库内的 Harness 工件：

```text
.harness/schemas/tasks.schema.json
.harness/templates/tasks.template.json
.harness/templates/plan.template.md
.harness/rules/workflow-lifecycle.md
.harness/scripts/state-write.py
.harness/scripts/select-next-task.py
```

如果未来要跨仓库复用，应先抽象这些依赖契约，再迁移为可安装通用 skill。

---

## 触发条件

建议 frontmatter：

```yaml
---
name: plan-writing
description: Use when creating or revising Harness active plan artifacts in a repository that contains .harness schemas, templates, rules, scripts, and work/plans.
---
```

description 只描述触发条件，不描述完整流程。原因是 Agent 可能只读 description 就自作主张，跳过 `SKILL.md` 正文。

应触发的场景：

- 用户要求将需求写成 Harness plan。
- backlog item 晋升为 L2/L3 plan。
- 已确认设计需要生成 `work/plans/active/<PLAN-ID>/plan.md`。
- `plan.md` 已审阅通过，需要 materialize 成 `tasks.json` / `handoff.md`。
- 修改 plan 后需要同步 `tasks.json`。

不应触发的场景：

- L0/L1 直接修复，无需正式 plan。
- 只是在解释 Harness 架构。
- 只是在执行现有 `tasks.json` 中的 task。
- 只是在归档已完成 plan。

---

## 从 Superpowers writing-plans 借鉴什么

Superpowers `writing-plans` 的价值在于计划质量控制，而不是文件格式。

应借鉴：

1. **面向零上下文执行者**
   - `plan.md` 必须让下一个 Agent 理解目标、范围、文件边界、任务拆分和验证策略。
   - 不依赖当前对话记忆。

2. **scope check**
   - 如果需求覆盖多个独立子系统，应拆成 L3 多阶段 plan。
   - 一个 plan 必须能产生可独立验证的工作成果。

3. **先列文件边界，再拆任务**
   - 先明确需要创建、修改、验证的文件。
   - 任务拆分应围绕文件边界和交付边界，而不是围绕聊天中的自然段落。

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

---

## Harness-native 边界

### plan.md 的边界

`plan.md` 应采用“任务契约型”边界，而不是“大纲型”或“Superpowers 执行手册型”。

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
- Run: `python3 -c 'import json; from pathlib import Path; from jsonschema import Draft202012Validator; schema=json.loads(Path(".harness/schemas/tasks.schema.json").read_text()); data=json.loads(Path(".harness/templates/tasks.template.json").read_text()); Draft202012Validator.check_schema(schema); errors=list(Draft202012Validator(schema).iter_errors(data)); raise SystemExit(1 if errors else 0)'`
- Check: no legacy `plan_section` / `depends_on` fields remain.
```

### tasks.json 的边界

`tasks.json` 保存执行状态和 gate 结果。它从审阅通过的 `plan.md` 抽取，不由 Agent 临时猜测。

必须由 `.harness/schemas/tasks.schema.json` 校验。

当前基础结构：

```json
{
  "$schema": "../../../.harness/schemas/tasks.schema.json",
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

后续若引入 code review gate，建议增加：

```json
{
  "review": {
    "checks": [],
    "findings": [],
    "lastResult": "not_run"
  }
}
```

### handoff.md 的边界

`handoff.md` 是恢复入口，不是状态真相源。它应摘要说明：

- 当前 plan 来源。
- 审阅结论。
- 初始 active task 建议。
- 风险与开放问题。
- 下一步原子动作。

状态仍以 `workflow-state.json` 与 `tasks.json` 为准。

---

## 核心流程

`plan-writing` skill 建议分为两个阶段，默认带审阅闸门。

### 阶段 1：Plan Draft

目标：只生成可审阅的 `plan.md`。

步骤：

1. 读取 Harness 上下文：
   - `harness-design/architecture.md`
   - `.harness/rules/workflow-lifecycle.md`
   - `.harness/schemas/tasks.schema.json`
   - `.harness/templates/tasks.template.json`

2. 判断任务等级：
   - L0/L1：不创建 plan，交给直接执行流程。
   - L2：创建单个 active plan。
   - L3：拆分为多个阶段性 plan 或在当前 plan 中明确分阶段 task。

3. 生成 `plan.md` 草案：
   - 写目标、范围、非范围。
   - 写文件边界。
   - 写实现方向。
   - 写任务契约区块。
   - 每个 task 带稳定 anchor。

4. Plan self-review：
   - 是否覆盖需求。
   - 是否无占位符。
   - 文件路径是否精确。
   - taskId 是否唯一。
   - planSection anchor 是否唯一。
   - 每个 task 是否有 acceptance。
   - 每个 task 是否有 verification commands 或 checks。
   - 是否把执行状态错误写入 plan。

5. 停下等待审阅：
   - 默认不生成 `tasks.json`。
   - 默认不切换 `activeTaskId`。
   - `workflow-state.currentPhase` 保持 `planning`。

硬规则：

```text
tasks.json MUST NOT be generated until plan.md has passed Plan Review,
unless the user explicitly requests one-shot materialization.
```

### 阶段 2：Plan Materialization

目标：将审阅通过的 `plan.md` 转化为完整 active plan package。

步骤：

1. 从 `plan.md` 的任务契约区块抽取 task manifest。
2. 生成 `work/plans/active/<PLAN-ID>/tasks.json`。
3. 使用 `.harness/schemas/tasks.schema.json` 校验。
4. 校验每个 task 的 `planSection` 能回链到 `plan.md` anchor。
5. 生成初始 `handoff.md`。
6. 调用或准备 `select-next-task.py` 选择第一个合法 task。
7. 输出给 `state-write.py` 使用的 patch。

初始 task 状态：

- `status = "idle"`
- `currentStep = ""`
- `nextAction = ""`
- `verification.lastResult = "not_run"`
- `review.lastResult = "not_run"`（若 schema 已引入）

---

## 脚本协作模型

skill 负责判断与编排，脚本负责确定性操作。

### materialize-tasks.py

建议新增脚本：

```text
.harness/scripts/materialize-tasks.py
```

职责：

- 输入已审阅的 `plan.md`。
- 解析结构化任务契约区块。
- 生成 `tasks.json`。
- 校验 `tasks.schema.json`。
- 校验 taskId 唯一。
- 校验 dependsOn 指向存在 task。
- 校验 planSection anchor 存在。
- 原子写入 `tasks.json`。

不负责：

- 判断需求范围。
- 决定任务如何拆分。
- 猜测自由文本中的任务。
- 判断 verification 是否语义充分。

### update-task.py

建议后续新增脚本：

```text
.harness/scripts/update-task.py
```

职责：

- 更新指定 `taskId` 的执行状态。
- 写入 currentStep / nextAction。
- 写入 verification 结果。
- 写入 review 结果。
- 校验 done 前置条件。
- 原子写回 `tasks.json`。

不负责：

- 判断测试输出是否真的表示通过。
- 判断 review finding 是否阻断。
- 决定 workflow 是否升级 / 降级。

### select-next-task.py

用于从合法候选 task 中选出下一任务，输出 state patch。它不直接写 `workflow-state.json`。

### state-write.py

仍是 `workflow-state.json` 唯一写入网关。plan-writing skill 只输出 patch 或调用它，不直接修改 state 文件。

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

### testing gate

由 `workflow-state.currentPhase = "testing"` 表示当前处于测试阶段。

testing 通过后，模型调用脚本回写：

```json
{
  "verification": {
    "commands": [
      "python3 -m json.tool .harness/templates/tasks.template.json"
    ],
    "checks": [
      "tasks.template.json uses taskId, planSection, and dependsOn"
    ],
    "lastResult": "passed"
  }
}
```

testing 失败时：

- `verification.lastResult = "failed"`。
- workflow 不得进入 `reviewing`。
- 当前 task 保持 `testing` 或回到 `implementing`。

### review gate

由 `workflow-state.currentPhase = "reviewing"` 表示当前处于 review 阶段。

review 通过后，模型调用脚本回写：

```json
{
  "review": {
    "checks": ["implementation matches acceptance"],
    "findings": [],
    "lastResult": "passed"
  }
}
```

review 失败时：

- `review.lastResult = "failed"`。
- 阻断 finding 写入 `review.findings` 摘要。
- workflow 回到 `implementing`。

详细测试输出和 review 过程不放入 `tasks.json`，应写入：

- `handoff.md`
- `work/sessions/YYYY-MM-DD/session-<id>.md`
- `closure.md`

---

## task done 判定

当前 task 进入 `done` 的前置条件：

1. `acceptance` 已满足。
2. `verification.lastResult == "passed"`。
3. `review.lastResult == "passed"`（引入 review block 后）。
4. 所有 `dependsOn` 中的任务均为 `done`。

`done` 不是口头声明，而是由 workflow gate 结果支撑的结构化状态。

---

## One-shot materialization 例外

默认流程必须有 Plan Review gate。但可支持用户显式要求一次性生成完整 package：

```text
请直接生成 plan.md、tasks.json 和 handoff.md
```

此时仍必须：

- 先在内部完成 plan self-review。
- 再生成 `tasks.json`。
- 再校验 schema。
- 最终向用户明确说明跳过了人工 plan review gate。

不允许在用户未显式要求时默认 one-shot。

---

## Skill 正文建议结构

正式 `SKILL.md` 可采用：

```md
---
name: plan-writing
description: Use when creating or revising Harness active plan artifacts in a repository that contains .harness schemas, templates, rules, scripts, and work/plans.
---

# Plan Writing

## Overview
Harness-native skill for creating reviewed active plan packages.

## When to Use
- Trigger on L2/L3 plan creation or revision.
- Do not trigger for L0/L1 direct work.

## Inputs and Dependencies
- Read `.harness/rules/workflow-lifecycle.md`.
- Read `.harness/schemas/tasks.schema.json`.
- Read `.harness/templates/tasks.template.json`.

## Output Package
- Create or revise `work/plans/active/<PLAN-ID>/plan.md`.
- Materialize `tasks.json` and `handoff.md` only after plan review.

## Phase 1: Plan Draft
- Draft only `plan.md`.
- Run the plan self-review checklist.
- Stop for review before task materialization.

## Plan Review Gate
- Require user or collaborator approval before generating `tasks.json`.
- Allow one-shot materialization only when explicitly requested.

## Phase 2: Materialization
- Extract structured task contracts.
- Generate `tasks.json`.
- Validate with `.harness/schemas/tasks.schema.json`.

## Tasks Extraction Rules
- Extract only from structured task contract sections.
- Require stable `planSection` anchors.
- Reject free-text task guessing.

## Testing and Review Gates
- Treat testing and review as workflow gates.
- Record gate results in the current task.

## Self-Review Checklist
- Check coverage, anchors, acceptance, verification, and forbidden execution state in `plan.md`.

## Common Mistakes
- Writing checkbox progress in `plan.md`.
- Generating `tasks.json` before plan review.
- Splitting testing or review into separate tasks.
```

如果正文超过 500 行，建议把详细示例移到：

```text
.harness/skills/plan-writing/references/examples.md
```

但第一版可以只保留一个 `SKILL.md`，避免过早拆分。

---

## Self-review checklist

Agent 完成 plan-writing 时必须检查：

- 是否正确判断 L0/L1/L2/L3。
- 是否只有 L2/L3 创建 plan package。
- `plan.md` 是否无 checkbox 执行状态。
- `plan.md` 是否无 `TBD` / `TODO` / 空泛语句。
- 每个 task 是否有唯一 `taskId`。
- 每个 task 是否有唯一稳定 anchor。
- 每个 task 是否有文件边界。
- 每个 task 是否有 acceptance。
- 每个 task 是否有 verification。
- `tasks.json` 是否由审阅后的 `plan.md` 抽取。
- `tasks.json` 是否通过 `.harness/schemas/tasks.schema.json`。
- `handoff.md` 是否只做恢复摘要，不替代 state。
- 是否通过 `state-write.py` 更新 workflow state。

---

## 压力场景

后续验证 skill 时，建议使用这些场景检查 Agent 是否会犯错：

1. **把 checkbox 写进 plan.md**
   - 期望：skill 阻止，要求执行状态进入 `tasks.json`。

2. **只写 plan.md，不生成 tasks.json**
   - 期望：Plan Draft 阶段允许；Materialization 阶段不允许。

3. **用户未审阅 plan.md 就生成 tasks.json**
   - 期望：默认阻止，除非用户显式 one-shot。

4. **从自由文本猜任务**
   - 期望：要求 `plan.md` 中存在结构化任务契约区块。

5. **把 testing/review 拆成独立 task**
   - 期望：阻止，要求作为 workflow gate 记录结果。

6. **没有 verification 的 task**
   - 期望：self-review 失败。

7. **planSection 使用人类标题**
   - 期望：要求稳定 anchor id。

8. **直接写 workflow-state.json**
   - 期望：要求通过 `state-write.py`。

这些压力场景可以作为后续 `writing-skills` 验证的测试用例。

---

## 未决问题

1. 是否现在就在 `tasks.schema.json` 中加入 `review` block，还是等 review-rules 成型后再加。
2. `materialize-tasks.py` 使用 Markdown anchor + 约定格式解析，还是要求 `plan.md` 内嵌 JSON/YAML task manifest。
3. `handoff.md` 初始模板是否由 plan-writing 直接生成，还是由单独 `handoff-writing` skill 负责。
4. `plan.md` 审阅通过状态是否需要在文件中显式标记，还是只依赖用户确认和会话记录。
5. L3 多阶段 plan 是单目录多阶段，还是多个 `PLAN-*` 顺序推进。

---

## 当前建议

第一版采用保守实现：

- 先写 `plan-writing` skill。
- 默认两阶段流程：Plan Draft → Plan Review → Materialization。
- `tasks.json` 只从结构化任务契约抽取。
- 暂不把脚本放入 skill 目录。
- 后续新增 `.harness/scripts/materialize-tasks.py`。
- review block 在 `review-rules.md` 定稿后再进入 `tasks.schema.json`。

这样可以先稳定 Agent 行为，再逐步把确定性部分脚本化。
