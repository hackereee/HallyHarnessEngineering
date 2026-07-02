# HallyHarnessEngineering

Languages: [中文](#中文版) | [English](#english-version)

## 中文版

HallyHarnessEngineering 是一个用于学习、验证和演进 Harness Engineering 工程标准的仓库。它把 Agent 工作流拆成可审计、可恢复、可验证的工程工件：规则由文档说明，结构由 JSON Schema 约束，状态写入由脚本网关控制，运行态数据集中落在 `work/`。

本仓库不是一个普通业务项目模板。它的核心交付是 Harness runtime framework、安装器生命周期、项目接入规则和可回归测试。

### 当前状态

- `.harness/` 已承载运行时框架资产：schema、template、rules、skills、scripts 和 tests。
- `work/` 承载当前仓库运行态：workflow state、active/archived plan package、backlog 和 session audit。
- `installer/` 定义外部安装器生命周期；安装器不属于 `.harness/` 运行时 gate。
- `pyproject.toml` 和 `src/harness_engineering_installer/` 承载当前 Python 包边界、固定资产 manifest、安装器引擎和 CLI 命令入口；当前包/命令标识是 `hally-harness-engineering`，当前版本是 `0.1.8`。
- `pipx install hally-harness-engineering` / `pipx upgrade hally-harness-engineering` 与 `uv tool install hally-harness-engineering` / `uv tool upgrade hally-harness-engineering` 是目标分发路径；PyPI 发布通过手动 release workflow 执行。
- `.harness` 固定框架资产的人类可读文本已标准化为英文，并由 `.harness/tests/test_language_standardization.py` 防止意外引入中文运行时框架文本。
- Harness entrypoint managed block 当前为 `harness-entrypoint-block-v2`，已将新 workflow 启动映射到 `start-workflow.py`，将 backlog consumption 映射到 `backlog-consume.py`。

### 权威入口

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | Agent 入口与事实来源。进入仓库后先读它，再按读取顺序核对规则、schema、脚本和测试。 |
| `.harness/ARCHITECTURE.md` | Harness 框架架构：目录分层、关键文件职责和核心不变量。 |
| `.harness/rules/task-level.md` | L0/L1/L2/L3 任务等级判断。 |
| `.harness/rules/workflow-lifecycle.md` | workflow-state、task status、ownerRole、phase 的生命周期语义。 |
| `.harness/rules/session-start.md` | 会话启动、首次 state bootstrap 和 session audit 边界。 |
| `.harness/rules/handoff-rules.md` | L2/L3 active plan 的 `handoff.md` 恢复摘要规则。 |
| `.harness/rules/llm-script-boundary.md` | 脚本与 LLM 的职责边界。 |
| `.harness/rules/workflow-gates.md` | `tasks.json` 与 testing/review gate 的边界。 |
| `.harness/rules/backlog-rules.md` | backlog intake、preempt 信号和 consumption audit 边界。 |
| `.harness/rules/archive-rules.md` | L2/L3 plan 归档与 L0/L1 direct workflow completion 规则。 |
| `installer/install-lifecycle.md` | 外部安装器安装、更新、自检和移交到 project-init 的生命周期。 |
| `learning-notes/` | 设计学习笔记，不作为运行态真相源。 |

### 目录边界

| 路径 | 职责 | 是否运行态 |
|---|---|---|
| `.harness/schemas/` | JSON Schema 2020-12 机器契约。 | 否 |
| `.harness/templates/` | 初始化模板和 Markdown 结构模板。 | 否 |
| `.harness/rules/` | schema 无法表达的语义规则。 | 否 |
| `.harness/skills/` | repo-local Agent 工作流技能。 | 否 |
| `.harness/scripts/` | 确定性脚本网关和统一 CLI。 | 否 |
| `.harness/tests/` | Harness schema、script、template 和规则回归测试。 | 否 |
| `.harness/contracts/` | 项目接入契约，如 project contracts 和 entrypoint metadata。 | 否 |
| `installer/` | 安装器生命周期文档和安装器自身测试。 | 否 |
| `src/harness_engineering_installer/` | Python 安装器包源码和固定资产 manifest。 | 否 |
| `work/` | 当前 workflow、plan、backlog、session audit 等运行态。 | 是 |
| `harness-design/` | 历史设计材料；不作为目标项目运行时资产。 | 否 |
| `learning-notes/` | 原理说明和学习笔记。 | 否 |

核心不变量：`.harness/` 只存契约、模板、规则、技能和工具；运行态数据属于 `work/`。`workflow-state.json` 不保存任务列表、历史流水或 plan 正文。

### 真相源与网关

- `work/workflow-state.json` 是 workflow 级运行态真相源。
- `work/plans/active/<PLAN-ID>/plan.md` 是 L2/L3 plan 契约。
- `work/plans/active/<PLAN-ID>/tasks.json` 是 task 级执行真相源。
- `work/plans/active/<PLAN-ID>/handoff.md` 是恢复摘要，不覆盖 JSON 真相源。
- `work/sessions/YYYY-MM-DD/session-<id>.md` 是会话审计证据，不驱动状态。
- `work/backlog/backlogs.json` 是 pending backlog 队列；`work/backlog/consumed.jsonl` 是消费审计。
- `.harness/contracts/project-contracts.json` 是目标项目环境检查契约。
- `.harness/contracts/project-entrypoints.json` 是目标项目 Agent 入口元数据契约。

写入边界必须保持清晰：

- `workflow-state.json` 只能由 `state-write.py` 写入；首次 bootstrap 仅允许 `session-start.py` 在 state 缺失且没有 active plan 时创建。
- `tasks.json` 只能由 `update-task.py` 写入 task 状态、验证结果和 review gate 摘要。
- `backlogs.json` 只能由 `backlog-intake.py` 追加 pending item。
- `consumed.jsonl` 只能由 `backlog-consume.py` 在下游 ownership evidence 已存在时写入。
- testing 和 review 是 workflow gate，不是独立 task。

### 工作流模型

任务等级按执行控制复杂度划分：

| 等级 | 含义 | Plan |
|---|---|---|
| L0 / direct-patch | 局部、低风险、无需正式规划的直接修补。 | 不创建 |
| L1 / verified-fix | 范围有限但必须定向验证的修复。 | 不创建 |
| L2 / planned-task | 需要先规划再执行的任务。 | 必须创建 |
| L3 / decomposed-epic | 必须拆成多个 task 或阶段性 plan 的复杂工作。 | 必须创建 |

workflow phase 与责任角色必须对齐：

| Phase | ownerRole |
|---|---|
| `planning` | `planner` |
| `implementing` | `developer` |
| `testing` | `tester` |
| `reviewing` | `reviewer` |
| `archiving` | `developer` |

L2/L3 在 `implementing`、`testing`、`reviewing` 阶段必须有且仅有一个 active task。task 进入 `done` 前必须有 acceptance、验证依据和结构化 review 依据，且 verification 与 review gate 都通过。

### 常用命令

从现有 workflow 恢复或启动会话：

```bash
python3 .harness/scripts/harness --root . session-start
```

运行 Harness 结构巡检和 workflow state 校验：

```bash
python3 .harness/scripts/harness --root . lint
python3 .harness/scripts/harness --root . validate-state
```

从终态开启新的 direct workflow：

```bash
python3 .harness/scripts/harness --root . start-workflow \
  --level L1 \
  --workflow-id workflow-adhoc-YYYYMMDD-001 \
  --next-action "Apply the first verifiable change"
```

记录进入 backlog 的新工作：

```bash
python3 .harness/scripts/harness --root . backlog-intake \
  --title "Short title" \
  --summary "Auditable summary of incoming work" \
  --source-ref "chat:YYYY-MM-DD-001" \
  --dispatch queue
```

运行项目环境契约检查：

```bash
python3 .harness/scripts/harness --root . check-project-env
```

运行回归测试：

```bash
python3 .harness/tests/test_language_standardization.py
python3 -m unittest discover -s .harness/tests -p 'test_*.py'
python3 -m unittest discover -s installer/tests -p 'test_*.py'
```

检查 `.harness` 英文化守卫时，`rg -n "\p{Han}" .harness` 应无命中；`ripgrep` 在无命中时返回 exit code 1，这是该检查的预期结果。

### 安装器边界

安装器的职责是把固定 `.harness/` 资产复制或更新到目标仓库，并保留目标仓库自己的运行态和项目文档。它必须保留 `work/` 和 `.harness/contracts/`，不得复制本仓库的 root `AGENTS.md`、`README.md` 或业务 `ARCHITECTURE.md` 到目标仓库。

目标包分发路径是：

```bash
pipx install hally-harness-engineering
pipx upgrade hally-harness-engineering
uv tool install hally-harness-engineering
uv tool upgrade hally-harness-engineering
```

CLI 命令形态是：

```bash
hally-harness-engineering --version
hally-harness-engineering install <target> --dry-run
hally-harness-engineering install <target>
hally-harness-engineering update <target>
hally-harness-engineering check <target>
```

发布到 TestPyPI 或 PyPI 前，必须先在本地构建并执行 artifact inspection 作为 pre-publish release gate：

```bash
python3 -m build
python3 installer/release/check_artifacts.py dist
python3 installer/release/smoke_install.py dist
```

该检查只验证本地 `dist/` 中的 wheel、sdist、metadata、console script、依赖、`.harness/` payload 和安装后的 CLI 行为，不发布包、不读取 registry credentials。

手动发布入口是 `.github/workflows/publish-python-package.yml`。完整 registry 操作、TestPyPI 验证、PyPI promotion、安装/升级命令和 yank/rollback 指南见 `docs/release/package-registry-release.md`。

本仓库内的运行时工作仍以 `.harness/scripts/harness` 为稳定入口；安装器 CLI 只负责复制、更新和检查固定 Harness 资产。

### 贡献和修改原则

- 修改前先看 `git status --short --branch`，不要覆盖已有用户改动。
- 改规则时同步检查 schema、template、script 和 test 是否需要更新。
- 能由 schema 表达的约束必须进入 `.harness/schemas/`，不要只写文档口号。
- 脚本负责确定性、可回归、可审计的操作；LLM 负责语义判断、计划、handoff、closure 和异常分析。
- 完成前说明实际执行过的验证；不要只说“应该可以”。

## English Version

HallyHarnessEngineering is a repository for learning, validating, and evolving Harness Engineering standards. It turns Agent workflows into auditable, recoverable, and verifiable engineering artifacts: rules are documented, structure is constrained by JSON Schema, state writes go through deterministic script gateways, and runtime data lives under `work/`.

This is not a normal application template. Its core deliverables are the Harness runtime framework, installer lifecycle, project onboarding rules, and regression tests.

### Current Status

- `.harness/` contains runtime framework assets: schemas, templates, rules, skills, scripts, and tests.
- `work/` contains this repository's runtime state: workflow state, active/archived plan packages, backlog, and session audit.
- `installer/` defines the external installer lifecycle; the installer is not a `.harness/` runtime gate.
- `pyproject.toml` and `src/harness_engineering_installer/` define the current Python package boundary, fixed asset manifest, installer engine, and CLI entrypoint; the current package/command identifier is `hally-harness-engineering`, and the current version is `0.1.9`.
- `pipx install hally-harness-engineering` / `pipx upgrade hally-harness-engineering` and `uv tool install hally-harness-engineering` / `uv tool upgrade hally-harness-engineering` are the target distribution paths. PyPI publication runs through the manual release workflow.
- Human-facing fixed framework text under `.harness` is standardized in English and guarded by `.harness/tests/test_language_standardization.py` against accidental Han text in runtime framework assets.
- The current Harness entrypoint managed block is `harness-entrypoint-block-v2`; it maps new workflow start to `start-workflow.py` and backlog consumption to `backlog-consume.py`.

### Authoritative Entry Points

| File | Purpose |
|---|---|
| `AGENTS.md` | Agent entrypoint and source of truth. Read it first, then follow its ordered references. |
| `.harness/ARCHITECTURE.md` | Harness framework architecture: layers, file responsibilities, and invariants. |
| `.harness/rules/task-level.md` | L0/L1/L2/L3 task level classification. |
| `.harness/rules/workflow-lifecycle.md` | Lifecycle semantics for workflow state, task status, ownerRole, and phase. |
| `.harness/rules/session-start.md` | Session startup, first state bootstrap, and session audit boundaries. |
| `.harness/rules/handoff-rules.md` | Recovery summary rules for L2/L3 active plan `handoff.md`. |
| `.harness/rules/llm-script-boundary.md` | Responsibility boundary between deterministic scripts and LLM semantic judgment. |
| `.harness/rules/workflow-gates.md` | Boundary between `tasks.json` and testing/review workflow gates. |
| `.harness/rules/backlog-rules.md` | Backlog intake, preempt signals, and consumption audit boundaries. |
| `.harness/rules/archive-rules.md` | L2/L3 plan archiving and L0/L1 direct workflow completion. |
| `installer/install-lifecycle.md` | External installer install, update, self-check, and project-init handoff lifecycle. |
| `learning-notes/` | Design notes and learning material, not runtime truth sources. |

### Directory Boundaries

| Path | Responsibility | Runtime state |
|---|---|---|
| `.harness/schemas/` | JSON Schema 2020-12 machine contracts. | No |
| `.harness/templates/` | Initialization templates and Markdown structure templates. | No |
| `.harness/rules/` | Semantic rules that schemas cannot express. | No |
| `.harness/skills/` | Repo-local Agent workflow skills. | No |
| `.harness/scripts/` | Deterministic script gateways and unified CLI. | No |
| `.harness/tests/` | Regression tests for Harness schemas, scripts, templates, and rules. | No |
| `.harness/contracts/` | Project onboarding contracts, such as project contracts and entrypoint metadata. | No |
| `installer/` | Installer lifecycle docs and installer tests. | No |
| `src/harness_engineering_installer/` | Python installer package source and fixed asset manifest. | No |
| `work/` | Current workflow, plan, backlog, and session audit data. | Yes |
| `harness-design/` | Historical design material; not a target project runtime asset. | No |
| `learning-notes/` | Principles and learning notes. | No |

Core invariant: `.harness/` stores contracts, templates, rules, skills, and tools only; runtime data belongs under `work/`. `workflow-state.json` must not store task lists, history streams, or plan prose.

### Truth Sources And Gateways

- `work/workflow-state.json` is the workflow-level runtime truth source.
- `work/plans/active/<PLAN-ID>/plan.md` is the L2/L3 plan contract.
- `work/plans/active/<PLAN-ID>/tasks.json` is the task-level execution truth source.
- `work/plans/active/<PLAN-ID>/handoff.md` is a recovery summary, not an override for JSON truth sources.
- `work/sessions/YYYY-MM-DD/session-<id>.md` is session audit evidence, not state.
- `work/backlog/backlogs.json` is the pending backlog queue; `work/backlog/consumed.jsonl` is the consumption audit log.
- `.harness/contracts/project-contracts.json` is the target project environment check contract.
- `.harness/contracts/project-entrypoints.json` is the target project Agent entrypoint metadata contract.

Write boundaries must stay explicit:

- `workflow-state.json` can only be written by `state-write.py`; the only bootstrap exception is `session-start.py` when state is missing and no active plan exists.
- `tasks.json` can only be updated by `update-task.py`.
- `backlogs.json` can only be appended by `backlog-intake.py`.
- `consumed.jsonl` can only be written by `backlog-consume.py` after downstream ownership evidence exists.
- Testing and review are workflow gates, not standalone tasks.

### Workflow Model

Task levels are based on execution control complexity:

| Level | Meaning | Plan |
|---|---|---|
| L0 / direct-patch | Local, low-risk direct patch. | Not created |
| L1 / verified-fix | Limited fix that requires targeted verification. | Not created |
| L2 / planned-task | Work that must be planned before execution. | Required |
| L3 / decomposed-epic | Complex work that must be split into tasks or staged plans. | Required |

Workflow phase and owner role must align:

| Phase | ownerRole |
|---|---|
| `planning` | `planner` |
| `implementing` | `developer` |
| `testing` | `tester` |
| `reviewing` | `reviewer` |
| `archiving` | `developer` |

L2/L3 workflows must have exactly one active task during `implementing`, `testing`, and `reviewing`. A task cannot enter `done` until its acceptance criteria, verification evidence, and structured review evidence are present and both verification and review gates have passed.

### Common Commands

Start or resume a Harness session:

```bash
python3 .harness/scripts/harness --root . session-start
```

Run Harness structure lint and workflow state validation:

```bash
python3 .harness/scripts/harness --root . lint
python3 .harness/scripts/harness --root . validate-state
```

Start a new direct workflow from a terminal state:

```bash
python3 .harness/scripts/harness --root . start-workflow \
  --level L1 \
  --workflow-id workflow-adhoc-YYYYMMDD-001 \
  --next-action "Apply the first verifiable change"
```

Record incoming work in backlog:

```bash
python3 .harness/scripts/harness --root . backlog-intake \
  --title "Short title" \
  --summary "Auditable summary of incoming work" \
  --source-ref "chat:YYYY-MM-DD-001" \
  --dispatch queue
```

Run the project environment contract checks:

```bash
python3 .harness/scripts/harness --root . check-project-env
```

Run regression tests:

```bash
python3 .harness/tests/test_language_standardization.py
python3 -m unittest discover -s .harness/tests -p 'test_*.py'
python3 -m unittest discover -s installer/tests -p 'test_*.py'
```

For the `.harness` language guard, `rg -n "\p{Han}" .harness` should report no matches. `ripgrep` returns exit code 1 when no matches are found; that is the expected result for this scan.

### Installer Boundary

The installer copies or updates fixed `.harness/` assets into a target repository while preserving the target repository's runtime data and project-owned documents. It must preserve `work/` and `.harness/contracts/`, and it must not copy this source repository's root `AGENTS.md`, `README.md`, or business `ARCHITECTURE.md` into the target repository.

The target package distribution paths are:

```bash
pipx install hally-harness-engineering
pipx upgrade hally-harness-engineering
uv tool install hally-harness-engineering
uv tool upgrade hally-harness-engineering
```

The CLI command shape is:

```bash
hally-harness-engineering --version
hally-harness-engineering install <target> --dry-run
hally-harness-engineering install <target>
hally-harness-engineering update <target>
hally-harness-engineering check <target>
```

Before publishing to TestPyPI or PyPI, build locally and run artifact inspection as the pre-publish release gate:

```bash
python3 -m build
python3 installer/release/check_artifacts.py dist
python3 installer/release/smoke_install.py dist
```

This check only validates the local `dist/` wheel, sdist, metadata, console script, dependency declaration, bundled `.harness/` payload, and installed CLI behavior. It does not publish a package or read registry credentials.

The manual publish entrypoint is `.github/workflows/publish-python-package.yml`. Full registry operation, TestPyPI validation, PyPI promotion, install/upgrade commands, and yank/rollback guidance live in `docs/release/package-registry-release.md`.

`.harness/scripts/harness` remains the stable runtime entrypoint inside this repository. The installer CLI is responsible only for copying, updating, and checking fixed Harness assets.

### Contribution And Change Rules

- Check `git status --short --branch` before editing, and do not overwrite existing user changes.
- When changing a rule, also check whether schemas, templates, scripts, and tests must change.
- Constraints that can be expressed by schema belong in `.harness/schemas/`, not only in prose.
- Scripts handle deterministic, repeatable, auditable operations; LLMs handle semantic judgment, planning, handoff, closure, and exception analysis.
- Before completion, report the verification commands that actually ran. Do not claim “should work” without evidence.
