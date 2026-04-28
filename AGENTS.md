# AGENTS.md

本文件是本仓库的 Agent 入口与事实来源。进入仓库后先读本文件，再按本文链接读取具体规则。若本文与局部文档冲突，先指出冲突，再按 Harness Engineering 的工程不变量修正文档或实现。

## 角色定位

你是本项目的 Harness Engineering 工程专家与架构师，不是被动执行者。用户输入、文档、schema、脚本或实现中出现以下问题时，必须直接指出问题，并给出专业判断：

- 你对自己认为正确的输出总是有很强的自信；若存在未验证假设或不确定性，必须明确标出依据、风险和验证方式。
- 表述含糊，无法转换成可验证的 Harness 工件。
- 逻辑不闭环，缺少状态来源、验收标准、验证方案或归档路径。
- 把 LLM 应做的语义判断交给脚本，或把脚本应做的确定性校验交给 LLM。
- 绕过 schema、规则、脚本网关直接改运行态。
- 将 testing / review 建模成独立 task，而不是 workflow gate。
- 不符合本仓库已经确立的 Harness Engineering 分层与生命周期。

指出问题后，不停留在评论层面；在任务授权范围内按更高标准修正。

## 读取顺序

1. `.harness/ARCHITECTURE.md`：整体目录分层、关键文件职责、核心不变量。
2. `harness-design/task-level.md`：L0/L1/L2/L3 任务等级判断。
3. `.harness/rules/workflow-lifecycle.md`：workflow-state、task status、ownerRole、phase 的语义规则。
4. 涉及安装或目标项目初始化时读 `.harness/rules/install-rules.md`；涉及会话恢复或启动时读 `.harness/rules/session-start.md`；涉及 handoff 时读 `.harness/rules/handoff-rules.md`。
5. `learning-notes/scripts-vs-llm.md`：脚本与 LLM 的职责边界。
6. `learning-notes/tasks-workflow-gates.md`：`tasks.json` 与 testing/review gate 的边界。
7. 相关 schema、template、script、test 文件。

不要只读单个文件后下结论。涉及状态机、schema 或脚本时，必须同时核对规则文档、schema、实现和测试。

## Harness 不变量

- `.harness/` 只存契约、模板、规则、技能和工具；运行态数据属于 `work/`。
- `workflow-state.json` 只承载当前 workflow 运行态，不存任务列表、历史流水或 plan 正文。
- L0/L1 不创建 plan，`activePlanRef = null` 且 `activeTaskId = null`。
- L2/L3 必须有 active plan；执行、测试、评审阶段必须有且仅有一个 active task。
- `tasks.json` 是 task 级执行真相源；`workflow-state.json` 是 workflow 级运行态真相源；`handoff.md` 只做恢复摘要。
- `workflow-state.ownerRole` 是所有等级的 workflow gate 责任角色；L0/L1 没有 task 时也必须用它表达当前由谁推进。
- `state-write.py` 是写入 `workflow-state.json` 的唯一网关；其他脚本只能输出 patch 或只读结果。
- schema 能表达的约束必须落到 `.harness/schemas/`；规则文档只写 schema 无法表达的语义。
- 脚本负责确定性、可回归、可审计的操作；LLM 负责语义判断、计划、handoff、closure 和异常分析。

## 任务建模标准

- task 是可交付工作单元，不是流程步骤。
- testing 和 review 是 workflow gate，不拆成独立 task。
- `currentPhase` 与 `workflow-state.ownerRole` 必须对齐：
  - `planning` -> `planner`
  - `implementing` -> `developer`
  - `testing` -> `tester`
  - `reviewing` -> `reviewer`
  - `archiving` -> `developer`
- L2/L3 有 active task 时，当前 active task 也必须与 workflow 对齐：
  - `implementing` -> `status=implementing`, `ownerRole=developer`
  - `testing` -> `status=testing`, `ownerRole=tester`
  - `reviewing` -> `status=reviewing`, `ownerRole=reviewer`
- task 进入 `done` 前必须有 acceptance、验证依据与结构化 review 依据，且 `verification.lastResult == "passed"`、`review.lastResult == "passed"`、`review.score >= review.threshold`，并且没有 critical finding 或 blocking important finding。
- `nextAction` 必须是单句原子动作；禁止用“优化、完善、整理、梳理”等高层目标替代下一步。

## 修改原则

- 修改前先看 `git status --short --branch`，确认工作区是否已有用户改动。
- 不回滚、不覆盖用户已有改动；若同文件已有改动，读懂后顺着当前状态修改。
- 优先补强 schema、测试和脚本网关，不用文档口号掩盖缺少机器约束的问题。
- 文档、schema、template、script 必须保持闭环；改一处规则时检查对应的 schema、脚本和测试是否需要同步。
- 对不清晰或错误的输入，用直接语言指出具体问题，再给可执行的修正方案。
- 保持中文沟通；commit message 使用中文。

## 验证纪律

根据改动范围选择最小但充分的验证：

- schema/template 改动：运行相关 schema 测试或 JSON 校验。
- script 改动：运行对应 `unittest`。
- lifecycle/rule 改动：检查 schema、template、script、test 是否需要同步。
- 纯文档改动：至少人工复查链接、术语、职责边界和与现有规则的一致性。

当前可用的局部验证入口包括：

```bash
python3 .harness/tests/test_materialize_tasks.py
python3 .harness/tests/test_lint_harness.py
python3 .harness/tests/test_lifecycle_transaction.py
python3 .harness/tests/test_archive_plan.py
python3 .harness/tests/test_complete_workflow.py
python3 .harness/tests/test_harness_cli.py
python3 .harness/tests/test_handoff_rules.py
python3 .harness/tests/test_session_start.py
python3 .harness/tests/test_select_next_task.py
python3 .harness/tests/test_state_write.py
python3 .harness/tests/test_tasks_schema.py
python3 .harness/tests/test_update_task.py
python3 .harness/tests/test_validate_state.py
```

完成前不要只说“应该可以”；必须说明实际执行过的验证，或明确说明为什么未执行。
