# 整体架构

```Plain text
repo/
├─ AGENTS.md                    # Agent 入口：Harness 的事实来源与导航
├─ README.md                    # 人类入口：项目概览、安装、使用
├─ ARCHITECTURE.md              # 可选：项目级架构说明（可并入 AGENTS.md）
│
├─ .harness/                    # Harness 脚手架：不变资产，跟随 repo 版本化
│  ├─ schemas/                  # 机器可校验契约（JSON Schema 2020-12）
│  │  ├─ workflow-state.schema.json
│  │  └─ tasks.schema.json
│  │
│  │  # 规划中的 schema：
│  │  # backlogs.schema.json
│  │
│  ├─ templates/                # 初始化样例（JSON 模板的 $schema 指向 schemas/）
│  │  ├─ workflow-state.template.json
│  │  ├─ plan.template.md
│  │  ├─ tasks.template.json
│  │  ├─ handoff.template.md
│  │  └─ closure.template.md
│  │
│  ├─ rules/                    # 人读规则文档：schema 无法表达的语义约定
│  │  ├─ workflow-lifecycle.md
│  │  └─ archive-rules.md
│  │
│  │  # 规划中的规则文档：
│  │  # session-start.md / handoff-rules.md / backlog-rules.md
│  │
│  ├─ skills/                   # Agent 工作流技能：指导 Harness 工件生产与维护
│  │  └─ plan-writing/
│  │     └─ SKILL.md           # 生成 L2/L3 active plan package 的 repo-local skill
│  │
│  ├─ scripts/                  # 自动化脚本，统一子命令入口
│  │  ├─ session-start.py       # 会话启动 preflight、首次 state bootstrap、审计快照
│  │  ├─ validate-state.py
│  │  ├─ materialize-tasks.py   # 从 plan.md 任务契约生成 tasks.json
│  │  ├─ update-task.py         # 唯一写 tasks.json task 状态的网关
│  │  ├─ select-next-task.py    # 只读选择下一个可执行 task，并输出 state patch 建议
│  │  ├─ state-write.py         # 唯一写 workflow-state.json 的网关
│  │  ├─ lifecycle-transaction.py # 生命周期流转事务协调器，编排 task/state/handoff 更新
│  │  ├─ archive-plan.py        # 归档 active plan package 并收口 workflow state
│  │  ├─ complete-workflow.py   # 收口 L0/L1 direct workflow 并写 session 审计
│  │  └─ lint-harness.py        # 只读巡检目录结构与 Harness 全局不变量
│  │
│  │  # 规划中的 lifecycle 工具：
│  │  # harness / check-env.py
│
│  └─ tests/                    # Harness 契约、脚本与模板的回归测试
│     └─ test_*.py
│
├─ work/                        # 运行态：随业务滚动、可被清理的数据
│  ├─ workflow-state.json       # 当前工作流运行态（顶部 $schema 指向 .harness/schemas/）
│  │
│  ├─ backlog/
│  │  └─ backlogs.json
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
└─ src/                         # 业务代码，与 Harness 完全解耦
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
| 业务 | `src/` | 独立 | 是 |

核心不变量：**`.harness/` 只写契约、模板、规则、技能与工具，`work/` 只写数据。** 运行态目录可被整体清空而不损坏 Harness。

## 关键文件说明

### 入口层
- **`AGENTS.md`**：Harness 的唯一入口与事实来源；Agent 启动时先读它，再按链接跳转。
- **`README.md`**：面向人类，项目概览、安装指南、使用说明。
- **`ARCHITECTURE.md`**：架构总览（即本文）；若内容较短可并入 `AGENTS.md`。

### `.harness/schemas/`
机器可校验契约。所有 schema 遵循 Draft 2020-12。
- `workflow-state.schema.json`：当前工作流运行态的结构与跨字段一致性。
- `tasks.schema.json`：plan 内部 tasks 列表的结构。
- `backlogs.schema.json`：规划中的需求池结构。

### `.harness/templates/`
初始化样例。JSON 模板顶部用 `$schema` 相对路径指向 `.harness/schemas/`，保证 IDE 可即时校验与补全；Markdown 模板提供结构化正文形态，由对应 skill 与脚本约束。

### `.harness/rules/`
只写 schema 无法表达的语义约定，例如"`nextAction` 必须是单句原子动作"、"阶段流转需要哪些工件与脚本网关"。避免与 schema 重复。

### `.harness/skills/`
面向 Agent 的过程层，用于指导 Agent 生产或维护 Harness 工件。skill 只描述工作流、判断标准与产物边界，不保存运行态，不替代 schema 校验，也不执行脚本应承担的确定性操作。

`.harness/skills/` 中的 skill 默认是 **repo-local skill**，服务于当前 Harness 工件体系；它可以借鉴通用 Agent skill 格式，但不承诺脱离 `.harness/` 的 schema、template、rules、scripts 独立运行。若未来需要跨仓库复用，应先抽象依赖契约，再迁移为可安装的通用 skill。

- **`plan-writing/SKILL.md`**：将需求、backlog item 或已确认设计转成 L2/L3 active plan package；使用 `plan.template.md` 与 `materialize-tasks.py`，但不激活 task、不写 `workflow-state.json`。

### `.harness/scripts/`
- **`session-start.py`**：会话启动编排器。执行 Harness 关键工件检查、环境检查、`lint-harness.py`、首次 `workflow-state.json` bootstrap、`validate-state.py`，并写入 `work/sessions/YYYY-MM-DD/session-<id>.md` 审计快照。它只允许在 `workflow-state.json` 缺失且没有 active plan 时创建首个 state；不得修改已有 state，不得激活 task，不得推进 phase。
- **`validate-state.py`**：三层校验——JSON Schema → 跨文件（`activeTaskId ∈ tasks.json`）→ 语义启发式。
- **`materialize-tasks.py`**：从已确认的 `plan.md` 任务契约区块生成 `tasks.json`，并校验 schema、taskId、anchor、dependsOn、文件边界、acceptance 与 verification；只写 plan 目录内的 `tasks.json`，不激活 task，不写 `workflow-state.json`。
- **`update-task.py`**：`tasks.json` 的 task 状态写入网关，负责更新 task `status`、`ownerRole`、`currentStep`、`nextAction`、`verification`、`blockedReason`，并校验 schema 与 `done` 前置条件。
- **`select-next-task.py`**：只读选择器。读取并校验 plan 的 `tasks.json`，在没有 active task 时选出第一个依赖均已 `done` 的 `idle` task；若全部 task 已 `done`，输出进入 `archiving` 的 state patch 建议。它不写 `tasks.json`，不写 `workflow-state.json`。
- **`state-write.py`**：`workflow-state.json` 的**唯一更新网关**。接收 JSON Patch（或显式字段），依次执行"读当前 state → 应用 patch → 校验 phase 转换路径 → 调 `validate-state` → 临时文件 + rename 原子落盘 → 追加变更日志"。除 `session-start.py` 创建首个 state 的 bootstrap 例外外，其他脚本一律只输出 patch，不直接写 state。
- **`lifecycle-transaction.py`**：生命周期流转事务协调器。对一次 transition 执行 preflight、隔离 dry-run、调用 `update-task.py` 与 `state-write.py`、追加 `handoff.md`、postflight；它不绕过底层写入网关。当前支持 `activate-next`、`start-testing`、`start-review`、`review-failed`、`review-passed`。
- **`archive-plan.py`**：归档工具。要求当前 workflow 处于 `archiving`、active plan 内所有 task 均为 `done`，并且 `closure.md` 已由 Agent 写好；脚本校验后将 active plan package 迁移到 `work/plans/archived/<PLAN-ID>/`，再经 `state-write.py` 将 workflow 收到 archived 形态。
- **`complete-workflow.py`**：L0/L1 direct workflow 收口工具。要求无 active plan、无 active task、当前处于 `reviewing/reviewer`，并要求调用方提供 verification evidence 与 review summary；脚本经 `state-write.py` 将 workflow 收到 `completed` 形态，并追加 `work/sessions/YYYY-MM-DD/workflow-completions.jsonl` 审计记录。
- **`lint-harness.py`**：只读巡检目录结构与全局不变量。覆盖 `work/` 初始态、单 active plan、active plan package 完整性、`activePlanRef` 与目录一致性、active task 数量，以及非网关脚本直接写 `workflow-state.json`。

### `.harness/tests/`
- **`test_*.py`**：Harness 契约、脚本与模板的回归测试。测试与生产脚本分目录存放，避免 `.harness/scripts/` 同时承担工具入口与测试集合两种职责。

规划中的 lifecycle 工具：
- **`harness`**：统一入口，子命令分发。例：`harness validate-state`、`harness archive-plan PLAN-001`。
- **`check-env.py`**：校验依赖（`python`、`jsonschema`、`git` 等）。失败不阻塞，只把报告交给 Agent 决策。
- **`lint-harness.py`**：目录结构与不变量巡检（如"`plans/active/` 下至多一个目录"）。

### `work/`
- **`workflow-state.json`**：只承载运行态；详见 `workflow-state.schema.json` 与规则文档。
- **`backlog/backlogs.json`**：规划中的需求池；后续由 `backlog-rules.md` 定义晋升流程。
- **`plans/active/<PLAN-ID>/`** 与 **`plans/archived/<PLAN-ID>/`**：active ↔ archived 目录对称，归档只需改一段路径。
- **`sessions/YYYY-MM-DD/session-<id>.md`**：会话启动与 Agent 语义记录。
- **`sessions/YYYY-MM-DD/workflow-completions.jsonl`**：L0/L1 direct workflow completion 审计记录；由 `complete-workflow.py` 追加，保存 verification evidence 与 review summary。

### `src/`
业务代码；不与 Harness 交叉，保证 Harness 可平移到任意工程。

## 关键不变量

1. **单活跃 plan**：`work/plans/active/` 任意时刻至多一个目录；当前由规则与 `lint-harness.py` 强制。
2. **schema-first**：凡能用 schema 表达的约束一律落到 `.harness/schemas/`，`.harness/rules/` 不得重复。
3. **路径对称**：active 与 archived 的 plan 路径只差一段（`active` ↔ `archived`），方便脚本机械迁移。
4. **入口唯一**：最终脚本对外统一走 `.harness/scripts/harness <subcmd>`；当前已落地脚本仍可直接运行。
5. **运行态可清**：`rm -rf work/` 只回到初始态，不损坏 Harness 自身。
6. **单写者**：`workflow-state.json` 的已有状态仅由 `state-write.py` 更新；`session-start.py` 只允许在 state 缺失且没有 active plan 时从模板创建首个 state。其他脚本若需修改 state，必须输出 patch 并经 `state-write.py` 落盘。`lint-harness.py` 会扫描生产脚本中对该文件的直接写操作（如 `open(..., 'w')`、`Path.write_text(...)` 指向该路径）并视为违规。
