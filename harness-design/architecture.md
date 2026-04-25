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
│  │  ├─ tasks.schema.json
│  │  └─ backlogs.schema.json
│  │
│  ├─ templates/                # 初始化样例（$schema 指向 schemas/）
│  │  ├─ plan.template.md
│  │  ├─ tasks.template.json
│  │  ├─ handoff.template.md
│  │  └─ closure.template.md
│  │
│  ├─ rules/                    # 人读规则文档：schema 无法表达的语义约定
│  │  ├─ session-start.md
│  │  ├─ workflow-lifecycle.md
│  │  ├─ handoff-rules.md
│  │  ├─ archive-rules.md
│  │  └─ backlog-rules.md
│  │
│  ├─ skills/                   # Agent 工作流技能：指导 Harness 工件生产与维护
│  │  └─ <skill-name>/
│  │     └─ SKILL.md
│  │
│  └─ scripts/                  # 自动化脚本，统一子命令入口
│     ├─ harness               # 总入口（薄壳；子命令分发到下列 .py）
│     ├─ check-env.py
│     ├─ session-start.py
│     ├─ validate-state.py
│     ├─ state-write.py        # 唯一写 workflow-state.json 的网关
│     ├─ select-next-task.py
│     ├─ sync-plan-to-state.py
│     ├─ archive-plan.py
│     └─ lint-harness.py
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
│        └─ session-<id>.md
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
- `backlogs.schema.json`：需求池结构。

### `.harness/templates/`
初始化样例，顶部用 `$schema` 相对路径指向 `.harness/schemas/`，保证 IDE 可即时校验与补全。

### `.harness/rules/`
只写 schema 无法表达的语义约定，例如"`nextAction` 必须是单句原子动作"、"session-start 的五个步骤"。避免与 schema 重复。

### `.harness/skills/`
面向 Agent 的过程层，用于指导 Agent 生产或维护 Harness 工件。skill 只描述工作流、判断标准与产物边界，不保存运行态，不替代 schema 校验，也不执行脚本应承担的确定性操作。

`.harness/skills/` 中的 skill 默认是 **repo-local skill**，服务于当前 Harness 工件体系；它可以借鉴通用 Agent skill 格式，但不承诺脱离 `.harness/` 的 schema、template、rules、scripts 独立运行。若未来需要跨仓库复用，应先抽象依赖契约，再迁移为可安装的通用 skill。

### `.harness/scripts/`
- **`harness`**：统一入口，子命令分发。例：`harness validate-state`、`harness archive-plan PLAN-001`。
- **`check-env.py`**：校验依赖（`python`、`jsonschema`、`git` 等）。失败不阻塞，只把报告交给 Agent 决策。
- **`session-start.py`**：会话启动编排；依次调用 `check-env`、`validate-state`、写 `work/sessions/.../session-<id>.md`。
- **`validate-state.py`**：三层校验——JSON Schema → 跨文件（`activeTaskId ∈ tasks.json`）→ 语义启发式。
- **`state-write.py`**：`workflow-state.json` 的**唯一写入网关**。接收 JSON Patch（或显式字段），依次执行"读当前 state → 应用 patch → 调 `validate-state` → 临时文件 + rename 原子落盘 → 追加变更日志"。其他脚本一律只输出 patch，不直接写 state。
- **`select-next-task.py`**：按 plan 的 `tasks.json` 选出下一个可执行任务；**只读**，输出 `activeTaskId` 变更的 patch，由调用方经 `state-write.py` 落盘。
- **`sync-plan-to-state.py`**：plan 或 tasks 变更后计算 state 差异；**只读**，输出 patch，由调用方经 `state-write.py` 落盘。
- **`archive-plan.py`**：将 `work/plans/active/<PLAN-ID>/` 原子迁移到 `work/plans/archived/<PLAN-ID>/` 并生成 `closure.md`。
- **`lint-harness.py`**：目录结构与不变量巡检（如"`plans/active/` 下至多一个目录"）。

### `work/`
- **`workflow-state.json`**：只承载运行态；详见 `workflow-state.schema.json` 与规则文档。
- **`backlog/backlogs.json`**：需求池；由 `backlog-rules.md` 定义晋升流程。
- **`plans/active/<PLAN-ID>/`** 与 **`plans/archived/<PLAN-ID>/`**：active ↔ archived 目录对称，归档只需改一段路径。
- **`sessions/YYYY-MM-DD/session-<id>.md`**：会话级审计记录，由 `session-start.py` 自动写入。

### `src/`
业务代码；不与 Harness 交叉，保证 Harness 可平移到任意工程。

## 关键不变量

1. **单活跃 plan**：`work/plans/active/` 任意时刻至多一个目录，由 `lint-harness.py` 强制。
2. **schema-first**：凡能用 schema 表达的约束一律落到 `.harness/schemas/`，`.harness/rules/` 不得重复。
3. **路径对称**：active 与 archived 的 plan 路径只差一段（`active` ↔ `archived`），方便脚本机械迁移。
4. **入口唯一**：脚本对外统一走 `.harness/scripts/harness <subcmd>`；内部 `.py` 不暴露给使用方。
5. **运行态可清**：`rm -rf work/` 只回到初始态，不损坏 Harness 自身。
6. **单写者**：`workflow-state.json` 仅由 `state-write.py` 写入；其他脚本若需修改 state，必须输出 patch 并经此入口落盘。`lint-harness.py` 扫描源码中对该文件的直接写操作（如 `open(..., 'w')`、`json.dump` 指向该路径）一律视为违规。
