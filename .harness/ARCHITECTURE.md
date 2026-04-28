# Harness Framework Architecture

本文件是 `.harness/` 框架架构的唯一事实来源，描述 Harness Engineering 的目录分层、关键文件职责与核心不变量。它是框架架构，不是目标项目 root `ARCHITECTURE.md` 的业务架构。

```Plain text
repo/
├─ AGENTS.md                    # Agent 入口：Harness 的事实来源与导航
├─ README.md                    # 人类入口：项目概览、安装、使用
├─ ARCHITECTURE.md              # 可选：真实项目业务架构，不承载 Harness 框架架构
│
├─ .harness/                    # Harness 脚手架：不变资产，跟随 repo 版本化
│  ├─ ARCHITECTURE.md           # Harness 框架架构，供真实项目 agent 入口引用
│  │
│  ├─ schemas/                  # 机器可校验契约（JSON Schema 2020-12）
│  │  ├─ workflow-state.schema.json
│  │  ├─ tasks.schema.json
│  │  ├─ backlogs.schema.json
│  │  ├─ backlog-consumption-event.schema.json
│  │  ├─ project-contracts.schema.json
│  │  └─ project-entrypoints.schema.json
│  │
│  ├─ templates/                # 初始化样例（JSON 模板的 $schema 指向 schemas/）
│  │  ├─ workflow-state.template.json
│  │  ├─ backlogs.template.json
│  │  ├─ project-contracts.template.json
│  │  ├─ project-entrypoints.template.json
│  │  ├─ entrypoint-managed-block.template.md
│  │  ├─ plan.template.md
│  │  ├─ tasks.template.json
│  │  ├─ handoff.template.md
│  │  └─ closure.template.md
│  │
│  ├─ contracts/                # 项目级契约目录；project-env-contract 前可为空
│  │  ├─ .gitkeep
│  │  ├─ project-contracts.json  # 由 project-env-contract 生成，供通用 runner 执行
│  │  └─ project-entrypoints.json # 由 project-init / init-project-entrypoint 生成
│  │
│  ├─ rules/                    # 人读规则文档：schema 无法表达的语义约定
│  │  ├─ workflow-lifecycle.md
│  │  ├─ archive-rules.md
│  │  ├─ backlog-rules.md
│  │  ├─ handoff-rules.md
│  │  └─ session-start.md
│  │
│  ├─ skills/                   # Agent 工作流技能：指导 Harness 工件生产与维护
│  │  ├─ project-init/
│  │  │  └─ SKILL.md           # 初始化目标项目接入 Harness 的顶层 repo-local skill
│  │  ├─ project-env-contract/
│  │  │  └─ SKILL.md           # 生成项目环境契约的 repo-local skill
│  │  ├─ plan-writing/
│  │  │  └─ SKILL.md           # 生成 L2/L3 active plan package 的 repo-local skill
│  │  └─ task-review/
│  │     └─ SKILL.md           # 生成结构化 task review gate 摘要的 repo-local skill
│  │
│  ├─ scripts/                  # 自动化脚本，统一子命令入口
│  │  ├─ harness                # 统一 CLI 入口，薄分发到现有脚本
│  │  ├─ session-start.py       # 会话启动 preflight、首次 state bootstrap、审计快照
│  │  ├─ validate-state.py
│  │  ├─ materialize-tasks.py   # 从已通过 Plan Review Gate 的 plan.md 任务契约生成 tasks.json
│  │  ├─ update-task.py         # 唯一写 tasks.json task 状态的网关
│  │  ├─ select-next-task.py    # 只读选择下一个可执行 task，并输出 state patch 建议
│  │  ├─ state-write.py         # 唯一写 workflow-state.json 的网关
│  │  ├─ start-workflow.py      # 从 completed/archived 终态开启新的 workflow
│  │  ├─ lifecycle-transaction.py # 生命周期流转事务协调器，编排 task/state/handoff 更新
│  │  ├─ commit-task.py         # task 完成后的 Git commit gate
│  │  ├─ archive-plan.py        # 归档 active plan package 并收口 workflow state
│  │  ├─ complete-workflow.py   # 收口 L0/L1 direct workflow 并写 session 审计
│  │  ├─ backlog-intake.py      # 追加 pending incoming work 到 work/backlog/backlogs.json
│  │  ├─ backlog-consume.py     # 消费 pending backlog item 并写 consumed.jsonl 审计
│  │  ├─ check-project-env.py   # 读取项目契约并执行声明式环境检查
│  │  ├─ init-project-entrypoint.py # 检测/创建/更新真实项目 Agent 入口 managed block
│  │  └─ lint-harness.py        # 只读巡检目录结构与 Harness 全局不变量
│  │
│  │  # 规划中的 lifecycle 工具：
│  │  # check-env.py
│
│  └─ tests/                    # Harness 契约、脚本与模板的回归测试
│     └─ test_*.py
│
├─ work/                        # 运行态：随业务滚动、可被清理的数据
│  ├─ workflow-state.json       # 当前工作流运行态（顶部 $schema 指向 .harness/schemas/）
│  │
│  ├─ backlog/
│  │  ├─ backlogs.json
│  │  └─ consumed.jsonl
│  │
│  ├─ plans/
│  │  ├─ active/
│  │  │  └─ PLAN-001/
│  │  │     ├─ plan.md
│  │  │     ├─ tasks.json
│  │  │     └─ handoff.md
│  │  └─ archived/
│  │     └─ PLAN-001/
│  │        ├─ plan.md
│  │        ├─ tasks.json
│  │        ├─ handoff.md
│  │        └─ closure.md
│  │
│  └─ sessions/                 # 会话级审计记录
│     └─ 2026-04-24/
│        ├─ session-<id>.md
│        └─ workflow-completions.jsonl
│
└─ <project code roots>/        # 业务代码根，由目标项目决定；可为 src/、apps/、services/、modules/ 等一个或多个目录
```

## 分层原则

| 层 | 目录 | 寿命 | 是否进 Git |
|---|---|---|---|
| 入口 | `AGENTS.md` / `README.md` / `ARCHITECTURE.md` | 长 | 是 |
| 契约 | `.harness/schemas/` | 长 | 是 |
| 样例 | `.harness/templates/` | 长 | 是 |
| 规则 | `.harness/rules/` | 长 | 是 |
| 技能 | `.harness/skills/` | 长 | 是 |
| 工具 | `.harness/scripts/` | 长 | 是 |
| 测试 | `.harness/tests/` | 长 | 是 |
| 运行态 | `work/` | 短 | 部分（`work/plans/*`、`work/sessions/*` 建议纳管；`workflow-state.json` 可选） |
| 业务 | 目标项目自定义代码根 | 独立 | 是 |

核心不变量：**`.harness/` 只写契约、模板、规则、技能与工具，`work/` 只写数据。** 运行态目录可被整体清空而不损坏 Harness。
Harness 只固定 `.harness/` 与 `work/` 两层边界；业务代码目录不属于 Harness 框架约束，由目标项目业务架构和 `.harness/contracts/project-contracts.json` 中的 `projectProfile.sourceRoots` 声明。

## 关键文件说明

### 入口层
- **`AGENTS.md`**：Harness 的唯一入口与事实来源；Agent 启动时先读它，再按链接跳转。
- **`README.md`**：面向人类，项目概览、安装指南、使用说明。
- **root `ARCHITECTURE.md`**：真实项目业务架构，描述业务模块、依赖、数据流、运行拓扑和项目边界；不承载 Harness 框架架构。
- **`.harness/ARCHITECTURE.md`**：Harness framework architecture 的稳定引用位置，真实项目的 agent 入口通过 managed block 引用它。

### `.harness/schemas/`
机器可校验契约。所有 schema 遵循 Draft 2020-12。
- `workflow-state.schema.json`：当前工作流运行态的结构与跨字段一致性。
- `tasks.schema.json`：plan 内部 tasks 列表的结构，包含 verification 与 review gate 摘要。
- `backlogs.schema.json`：intake-side pending backlog queue 的结构契约；记录尚未被 workflow 或 plan 接管的 incoming work，不激活 plan/task，也不修改 workflow state。
- `backlog-consumption-event.schema.json`：backlog item 被下游 workflow 或 plan 接管后写入 `work/backlog/consumed.jsonl` 的审计事件契约，保留完整原 item、消费时间、目标引用和原因。
- `project-contracts.schema.json`：项目环境契约的结构；约束 project profile、source roots、command registry、environment checks、severity 与 adapter fallback metadata。
- `project-entrypoints.schema.json`：真实项目 Agent 入口契约的结构；约束 canonical entry、detected entries、managed block 状态与 `.harness/ARCHITECTURE.md` 引用。

### `.harness/templates/`
初始化样例。JSON 模板顶部用 `$schema` 相对路径指向 `.harness/schemas/`，保证 IDE 可即时校验与补全；Markdown 模板提供结构化正文形态，由对应 skill 与脚本约束。`entrypoint-managed-block.template.md` 是目标 agent entrypoint 中 Harness managed block 的固定版本化文案来源，`init-project-entrypoint.py` 只负责读取、校验 marker/version 并做确定性替换，不在 Python 字符串里维护长文案。

### `.harness/contracts/`
项目级契约目录。目录本身随 Harness 版本化，`project-contracts.json may be absent until project-env-contract configures it`；缺失时 `.harness/scripts/check-project-env.py` 返回 `NOT_CONFIGURED`，表示项目环境契约尚未初始化，而不是 Harness 核心损坏。`project-env-contract` 的默认输出是 `.harness/contracts/project-contracts.json`，它是 project environment checks 的 truth source。`.harness/scripts/check-project-env.py` 只能读取该契约并执行其中声明的 command 或 probe；它不得从仓库自由推断项目事实，也不得替代 `session-start.py`。

`project-entrypoints.json` 由 `project-init` skill 通过 `.harness/scripts/init-project-entrypoint.py` 生成或更新，用来记录真实项目 canonical agent entrypoint、已发现入口、managed block 状态、managed block 版本、root `ARCHITECTURE.md` 业务架构引用和 `.harness/ARCHITECTURE.md` 框架架构引用。`project-entrypoints.json` is deterministic entrypoint metadata, not a semantic conflict report；目标入口中的 workflow、task、testing、review、commit、handoff、backlog 或 archive 语义冲突由 Agent 在 `project-init` 过程中判断并报告，不写入该契约。缺失表示入口契约尚未配置，不代表 Harness 核心损坏；但 schema、template 与脚本本身属于 Harness core assets。

### Target Agent Entrypoint Integration

`project-init` 负责 target agent entrypoint integration。它是一个 workflow mapping layer：读取目标项目已存在的 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md`、Copilot instructions 或编辑器规则后，把目标项目的启动、规划、开发、测试、评审、提交、交接、backlog 与归档语义映射到 Harness lifecycle，而不是在目标仓库里创造第二套状态机。

边界如下：

- root `ARCHITECTURE.md` remains target project business architecture；它只描述目标项目业务模块、依赖、数据流、运行拓扑和项目边界。
- `.harness/ARCHITECTURE.md` remains Harness framework architecture；它只描述 Harness 分层、生命周期、schema、template、rules、skills、scripts 与 `work/` 运行态边界。
- `.harness/contracts/project-entrypoints.json` 只保存 canonical entrypoint、detected entries、managed block 状态和版本等确定性事实。
- 语义冲突 review 只属于 Agent 输出、session audit、handoff 或后续计划，不属于 schema/script 可判定的 entrypoint contract。
- `.harness/scripts/init-project-entrypoint.py` 只能创建或替换 `harness-engineering` managed block、确保 root `ARCHITECTURE.md` 存在并写入 entrypoint contract；它不得解析自由文本来判断工作流冲突。

### `.harness/rules/`
只写 schema 无法表达的语义约定，例如"`nextAction` 必须是单句原子动作"、"阶段流转需要哪些工件与脚本网关"。避免与 schema 重复。
- `backlog-rules.md`：定义 backlog intake 的 `queue` / `preempt` 语义、pending queue 边界与 consumption audit；intake 与 consume 都不直接改变 active workflow。
- `handoff-rules.md`：定义 L2/L3 active plan `handoff.md` 的结构、恢复摘要边界与 lifecycle transaction 记录形态；`handoff.md` 不是 truth source。
- `session-start.md`：定义 session 启动的三条路径、首次 state bootstrap 边界、existing state read-only 约束与 session audit 文件语义。

### `.harness/skills/`
面向 Agent 的过程层，用于指导 Agent 生产或维护 Harness 工件。skill 只描述工作流、判断标准与产物边界，不保存运行态，不替代 schema 校验，也不执行脚本应承担的确定性操作。

`.harness/skills/` 中的 skill 默认是 **repo-local skill**，服务于当前 Harness 工件体系；它可以借鉴通用 Agent skill 格式，但不承诺脱离 `.harness/` 的 schema、template、rules、scripts 独立运行。若未来需要跨仓库复用，应先抽象依赖契约，再迁移为可安装的通用 skill。

- **`.harness/skills/project-init/SKILL.md`**：初始化 Harness 到目标开发仓库时使用的顶层语义 skill；负责入口文档发现、Harness 架构引用落位和子流程编排，不直接替代确定性脚本。
- **`.harness/skills/project-env-contract/SKILL.md`**：生成项目环境契约的语义 skill；指导 Agent 先读取仓库证据，再生成 `.harness/contracts/project-contracts.json`，其中包含 project profile、environment checks 与 command registry。project environment differences belong in project contracts, not in `session-start.py`；`session-start.py` 只校验 Harness 启动所需的核心资产与运行态形态。
- **`plan-writing/SKILL.md`**：将需求、backlog item 或已确认设计转成 L2/L3 active plan package；先记录预期 Architecture Impact，再完成 planning-time `Plan Review Gate` 并在 `plan.md` 记录 `Status: passed`，最后使用 `materialize-tasks.py` 生成 `tasks.json`，但不激活 task、不写 `workflow-state.json`。
- **`task-review/SKILL.md`**：根据实现、plan/task acceptance、验证证据、Architecture Impact 和 diff 生成结构化 review 摘要；输出给 `update-task.py` 使用，不直接写 `tasks.json` 或 `workflow-state.json`。

### `.harness/scripts/`
- **`harness`**：统一 CLI 入口。它只做参数归一和薄分发，不重新实现生命周期逻辑；`validate-state` 子命令默认校验 `work/workflow-state.json`。
- **`session-start.py`**：会话启动编排器。执行 Harness 关键工件检查（含 repo-local core skills）、环境检查、`lint-harness.py`、首次 `workflow-state.json` bootstrap、`validate-state.py`，并写入 `work/sessions/YYYY-MM-DD/session-<id>.md` 审计快照。它只允许在 `workflow-state.json` 缺失且没有 active plan 时创建首个 state；不得修改已有 state，不得激活 task，不得推进 phase。
- **`validate-state.py`**：三层校验——JSON Schema → 跨文件（`activeTaskId ∈ tasks.json`）→ 语义启发式。
- **`materialize-tasks.py`**：从已通过 `Plan Review Gate` 的 `plan.md` 任务契约区块生成 `tasks.json`，并校验 schema、taskId、anchor、dependsOn 存在性与无环性、文件边界、acceptance 与 verification；只写 plan 目录内的 `tasks.json`，初始化 `review.lastResult=not_run`，不激活 task，不写 `workflow-state.json`。
- **`update-task.py`**：`tasks.json` 的 task 状态写入网关，负责更新 task `status`、`ownerRole`、`currentStep`、`nextAction`、`verification`、`review`、`blockedReason`，并校验 schema 与 `done` 前置条件。
- **`select-next-task.py`**：只读选择器。读取并校验 plan 的 `tasks.json`，在没有 active task 时选出第一个依赖均已 `done` 的 `idle` task；若全部 task 已 `done`，输出进入 `archiving` 的 state patch 建议。它不写 `tasks.json`，不写 `workflow-state.json`。
- **`state-write.py`**：`workflow-state.json` 的**唯一更新网关**。接收 JSON Patch（或显式字段），依次执行"读当前 state → 应用 patch → 校验 phase 转换路径、workflowId 不变性、terminal reset / terminal close 与关键前置条件 → 调 `validate-state` → 预检变更日志可写 → 临时文件 + rename 原子落盘 → 追加变更日志"。其中 `reviewing → archiving` 会回读 active plan 的 `tasks.json`，确认 active task 与 plan 全部 task 均已 `done`；`completed` / `archived` 重新进入 `active` 必须显式走 terminal reset 并使用新的 `workflowId`；planned terminal reset 还要求 active plan `Plan Review Gate` 为 `Status: passed`；`active` 收口到 `completed` / `archived` 必须显式使用 `--allow-terminal-close`，且不得残留 active plan 目录。除 `session-start.py` 创建首个 state 的 bootstrap 例外外，其他脚本一律只输出 patch，不直接写 state。
- **`start-workflow.py`**：新 workflow 启动工具。只允许从 `completed` / `archived` 终态开启新的 `active` workflow；direct L0/L1 进入 `implementing/developer`，planned L2/L3 绑定已存在 active plan package 并进入 `planning/planner`。脚本先在隔离副本里 dry-run，再通过 `state-write.py --allow-terminal-reset` 写入真实 state，并执行 lint / validate postflight。
- **`lifecycle-transaction.py`**：生命周期流转事务协调器。对一次 transition 执行 preflight、隔离 dry-run、调用 `update-task.py` 与 `state-write.py`、追加 `handoff.md`、postflight；它不绕过底层写入网关。当前支持 `activate-next`、`start-testing`、`start-review`、`review-failed`、`review-passed`，其中 review 流转消费 `tasks.json` 中的结构化 review gate。
- **`commit-task.py`**：L2/L3 task 完成提交 gate。只在 `lifecycle-transaction.py review-passed` 成功后运行，确认目标 task 已 `done` 且 verification/review 均 passed，再执行 `git add -A` 与 `git commit`。它允许同一次提交包含 `review-passed` 产生的下一个 task 激活状态变更；它不写 `workflow-state.json`、不写 `tasks.json`，也不替代 lifecycle transition。
- **`archive-plan.py`**：归档工具。要求当前 workflow 处于 `archiving`、active plan 内所有 task 均为 `done`，并且 `closure.md` 已由 Agent 写好且包含 `Architecture Impact`；脚本还通过 Git worktree 边界确认 `commit-task.py` 已提交 task 完成结果，归档前只允许当前 plan 的 `closure.md` 存在未提交变化；校验后将 active plan package 迁移到 `work/plans/archived/<PLAN-ID>/`，再经 `state-write.py --allow-terminal-close` 将 workflow 收到 archived 形态。
- **`complete-workflow.py`**：L0/L1 direct workflow 收口工具。要求无 active plan、无 active task、当前处于 `reviewing/reviewer`，并要求调用方提供 verification evidence、review summary 与 architecture impact summary；脚本先预检 completion audit 可写，再经 `state-write.py --allow-terminal-close` 将 workflow 收到 `completed` 形态，并以临时文件替换方式追加 `work/sessions/YYYY-MM-DD/workflow-completions.jsonl` 审计记录。
- **`backlog-intake.py`**：backlog intake 写入网关。它从 `.harness/templates/backlogs.template.json` 初始化缺失的 `work/backlog/backlogs.json`，按 `nextId` 分配 `BL-NNN` 并递增游标，校验完整 store 后原子追加；旧 store 缺少 `nextId` 时按 `max(existing BL-NNN) + 1` 迁移。它不写 `workflow-state.json`、`tasks.json` 或 active plan 文件；`preempt` 只请求 LLM 评估，不自动中断当前 workflow。
- **`backlog-consume.py`**：backlog consumption 写入网关。它只在下游 ownership evidence 已存在时把 item 从 `work/backlog/backlogs.json` 移除，并把 schema-valid 事件追加到 `work/backlog/consumed.jsonl`。`plan:<PLAN-ID>` 目标要求 active plan package 完整、Plan Review Gate passed、`tasks.json` 合法且 plan/handoff 引用 backlog id 或 `sourceRef`；`workflow:<workflowId>` 目标要求 validated direct workflow state 和 session audit source reference。若消费事件写入后 pending store 写回失败，脚本必须回滚刚写入的 consumed event，避免 item 同时存在于 pending 与 consumed 审计中。它不写 `workflow-state.json`、`tasks.json`、active plan 文件或 `handoff.md`。
- **`check-project-env.py`**：项目环境契约执行器。它先按 `.harness/schemas/project-contracts.schema.json` 校验 `.harness/contracts/project-contracts.json` 或调用方传入的 contract，再校验 command / check ID 唯一性与 `commandRef` 引用完整性，最后执行 contract 声明的 command / probe。contracts 是 truth source；runner 不写 `workflow-state.json`、不写 `tasks.json`，也不会在 `session-start.py` 中自动执行。
- **`init-project-entrypoint.py`**：真实项目 Agent 入口执行器。它检测 `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` 等入口，缺失时返回 `NEEDS_ENTRYPOINT`，并且只通过唯一的 `harness-engineering` managed block 创建或更新入口引用；managed block 内容来自 `.harness/templates/entrypoint-managed-block.template.md`，脚本只校验 marker 与 block version 后做确定性替换；若已有多个或不成对的 managed block marker 则阻断，避免重复入口指令；执行写入时若 root `ARCHITECTURE.md` 缺失，会创建空文件，为后续 task completion summary 判断是否归纳更新业务架构做准备；最后写入 `.harness/contracts/project-entrypoints.json`。它不写 workflow/task 运行态。
- **`lint-harness.py`**：只读巡检目录结构与全局不变量。覆盖 `work/` 初始态、单 active plan、active plan package 完整性、active `handoff.md` 结构、`activePlanRef` 与目录一致性、active task 数量，以及 `.harness/scripts/` 下 Python 与无扩展名生产脚本直接写 `workflow-state.json`。

### `.harness/tests/`
- **`test_*.py`**：Harness 契约、脚本与模板的回归测试。测试与生产脚本分目录存放，避免 `.harness/scripts/` 同时承担工具入口与测试集合两种职责。

规划中的 lifecycle 工具：
- **`check-env.py`**：校验依赖（`python`、`jsonschema`、`git` 等）。失败不阻塞，只把报告交给 Agent 决策。

### `work/`
- **`workflow-state.json`**：只承载运行态；详见 `workflow-state.schema.json` 与规则文档。
- **`backlog/backlogs.json`**：backlog intake 的 pending queue，结构由 `.harness/schemas/backlogs.schema.json` 约束，初始形态来自 `.harness/templates/backlogs.template.json`。它只保存尚未被 workflow 或 plan 接管的 incoming work，不是 active plan，也不驱动当前 workflow 阶段。
- **`backlog/consumed.jsonl`**：backlog consumption 审计日志，每行由 `.harness/schemas/backlog-consumption-event.schema.json` 约束，记录被移出 pending queue 的完整原 item、消费时间、目标引用和原因。
- **`plans/active/<PLAN-ID>/`** 与 **`plans/archived/<PLAN-ID>/`**：active ↔ archived 目录对称，归档只需改一段路径。
- **`sessions/YYYY-MM-DD/session-<id>.md`**：会话启动与 Agent 语义记录；它是审计证据，不是 workflow/task truth source。
- **`sessions/YYYY-MM-DD/workflow-completions.jsonl`**：L0/L1 direct workflow completion 审计记录；由 `complete-workflow.py` 追加，保存 verification evidence、review summary 与 architecture impact summary。

### Project code roots
业务代码根由目标项目决定，可以是单一 `src/`，也可以是 `.NET` solution、Java multi-module、monorepo 或前后端混合仓库中的多个目录，例如 `apps/`、`services/`、`packages/`、`modules/` 或语言生态惯用路径。Harness 不规定业务目录名称，只要求业务代码不与 `.harness/` 框架资产和 `work/` 运行态交叉。

确定性项目事实写入 `.harness/contracts/project-contracts.json` 的 `projectProfile.sourceRoots`；业务模块、依赖、数据流、运行拓扑和项目边界仍由 root `ARCHITECTURE.md` 描述。

## 关键不变量

1. **单活跃 plan**：`work/plans/active/` 任意时刻至多一个目录；当前由规则与 `lint-harness.py` 强制。
2. **schema-first**：凡能用 schema 表达的约束一律落到 `.harness/schemas/`，`.harness/rules/` 不得重复。
3. **路径对称**：active 与 archived 的 plan 路径只差一段（`active` ↔ `archived`），方便脚本机械迁移。
4. **入口统一**：常规外部调用走 `.harness/scripts/harness <subcmd>`；底层脚本保持可直接运行，供测试、调试和脚本编排使用。
5. **运行态可清**：`rm -rf work/` 只回到初始态，不损坏 Harness 自身。
6. **单写者**：`workflow-state.json` 的已有状态仅由 `state-write.py` 更新；`session-start.py` 只允许在 state 缺失且没有 active plan 时从模板创建首个 state。其他脚本若需修改 state，必须输出 patch 并经 `state-write.py` 落盘。`lint-harness.py` 会扫描 `.harness/scripts/` 下 Python 与无扩展名生产脚本中对该文件的直接写操作（如 `open(..., 'w')`、`Path.write_text(...)` 指向该路径）并视为违规。
7. **task 完成即提交**：L2/L3 每个 task 经 `review-passed` 进入 `done` 后，必须运行 `commit-task.py --task <TASK-ID>` 生成 Git 提交，再开始下一项实现或归档 closure。commit gate 不是 task，不改变 state/tasks，只审计已完成 task 的交付边界。
