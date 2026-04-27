# workflow-lifecycle.md

`workflow-state.json` 的流转规则与语义约定。**只写 schema 无法表达的内容**——结构、枚举、跨字段约束已落到 `workflow-state.schema.json` / `tasks.schema.json`，本文不重复。

涵盖：任务等级 ↔ state 形态映射、workflow 粒度、阶段转换、责任角色、单活跃任务不变量、等级升降级、与 handoff/archive 的衔接。

定位：`.harness/rules/` 规则层文档。配套 schema、`task-level.md`、`validate-state.py`、`state-write.py` 共同约束任务从创建到归档的全过程。

---

## 1. 任务等级 ↔ state 形态映射

任务等级定义见 `task-level.md`。等级直接决定 `workflow-state.json` 的合法形态：

| 等级 | 触发条件 | activePlanRef | activeTaskId | 审计锚点 | plan.md / tasks.json |
|---|---|---|---|---|---|
| L0 / direct-patch | 局部、低风险、无需正式规划 | `null` | `null` | `workflowId` | 不创建 |
| L1 / verified-fix | 范围有限的修复，需定向验证 | `null` | `null` | `workflowId` | 不创建 |
| L2 / planned-task | 需先规划再执行 | `./plans/active/<PLAN-ID>/plan.md` | planning/archiving 为 `null`；implementing/testing/reviewing 为 `tasks.json` 中某条 taskId | 执行阶段为 `activeTaskId`；planning/archiving 为 `workflowId` + `activePlanRef` | 必须创建 |
| L3 / decomposed-epic | 须拆为多子任务或阶段性 plan | 同上（每段独立 plan） | 同上 | 同上 | 必须创建，可能多份顺序推进 |

**不变量**：
- L0/L1 期间 `work/plans/active/` 必须为空。残留即视为状态不一致；当前由 Agent 复查，后续由 `lint-harness.py` 巡检。
- L2/L3 期间 `activePlanRef` 指向的 plan 目录必须存在 `plan.md` 与 `tasks.json`。
- 所有等级都必须在 `workflow-state.json` 中写入 `ownerRole`。L0/L1 没有 `tasks.json`，因此只能通过 `workflow-state.ownerRole` 表达当前 workflow gate 的责任角色。

---

## 2. workflow 粒度

工作流是**任务级**容器：一个 workflow 对应一次完整的"接需求 → 执行 → 归档"。

- `workflowId` 创建后不变，命名应携带任务语义，便于审计追溯。
  - L0/L1 推荐：`workflow-fix-<slug>-<yyyymmdd>-v1`、`workflow-adhoc-<yyyymmdd>-NNN`
  - L2/L3 推荐：`workflow-plan-<NNN>-v1`
- 一个 workflow 完成后必须流转至 `completed` 或 `archived`，再开下一个。**禁止复用 workflowId 承接新需求**。
- 同一时刻 `work/workflow-state.json` 只承载一个 workflow 的运行态。
- `workflowStatus` 当前只支持 `active`、`completed`、`archived`。`paused` 不是受支持的运行态；若未来需要暂停/恢复，必须先补齐 schema、phase 转换、resume 前置条件和 lifecycle 脚本测试。

---

## 3. 阶段转换

`currentPhase` 的合法转换图（schema 只校验枚举与单点跨字段约束，转换路径属规则层）：

```
planning ──► implementing ──► testing ──► reviewing ──► archiving
   ▲             ▲                           │               │
   │             └──── review failed ◄───────┘               │
   │             │                                           │
   │             └─► (回退) planning  (仅在范围重定义时)        |
   └──────────────────── (新 workflow) ◄─────────────────────┘
```

**转换前置条件**：

| 转换 | 前置 |
|---|---|
| `planning → implementing` | L2/L3：`plan.md` + `tasks.json` 已落盘且 schema 校验通过；待激活 task 已选定，并准备同步写入 task 状态与 workflow state。L0/L1：跳过 planning，启动即 implementing。|
| `implementing → testing` | 当前 task 的实现产物已具备可验证形态（命令/检查项可跑）。|
| `testing → reviewing` | `verification.lastResult == "passed"`。|
| `reviewing → implementing` | 两种场景：`review.lastResult=failed` 时当前 task 回到实现阶段；结构化 review passed 且仍有可执行 idle task 时，当前 task 置为 `done` 并激活下一个 task。两者都必须刷新 `nextAction`。|
| `reviewing → completed` | L0/L1：无 active plan、无 active task；验证证据与 review summary 已准备写入 session 审计。|
| `reviewing → archiving` | L2/L3：结构化 review passed；当前 task 已 `done`；plan 已无未完成 task。|
| `archiving → archived` | L2/L3：Agent 已写好 `closure.md`；`archive-plan.py` 完成迁移并将 workflowStatus 置为 `archived`。|

**禁止跳跃**：例如 `planning → testing` 直接跳过 implementing 是非法的，由 `state-write.py` 基于写入前后的 `currentPhase` 检查（schema 与 `validate-state.py` 只能校验当前形态，无法单独判断历史转换路径）。`reviewing → archiving` 还必须由 `state-write.py` 回读 active plan 的 `tasks.json`，确认写入前 active task 已 `done` 且 plan 内所有 task 均为 `done`。

**回退**：仅允许 `implementing → planning`，且必须伴随 plan/tasks 的范围调整记录（写入 handoff）。其他回退一律视为非法。

**terminal reset**：`completed` / `archived` 重新进入 `active` 是 workflow 级重置，不是普通 phase 变更。即使 `currentPhase` 未变化，也必须经 `start-workflow.py` 调用 `state-write.py --allow-terminal-reset`，显式写入新的 `workflowId`、`workflowStatus=active`、`activePlanRef`、`activeTaskId`、`currentPhase`、`ownerRole`、`nextAction`。

### 3.1 workflow ownerRole 与 task ownerRole

`workflow-state.ownerRole` 是 workflow gate 级责任角色，适用于 L0-L3。它由 `currentPhase` 决定：

| workflow phase | workflow-state.ownerRole | 语义 |
|---|---|---|
| `planning` | `planner` | 规划者生成或修正 plan package。 |
| `implementing` | `developer` | 开发者实现当前 workflow 工作单元。 |
| `testing` | `tester` | 测试者执行 verification commands / checks。 |
| `reviewing` | `reviewer` | 评审者检查实现是否满足 acceptance、工程边界与 Harness 不变量。 |
| `archiving` | `developer` | 开发者执行归档动作，生成 closure 并完成状态收口。 |

`tasks.json` 是 task 级执行真相源，必须能表达当前 task 由哪个角色推进。L2/L3 有 active task 时，`workflow-state.currentPhase`、`workflow-state.ownerRole` 与当前 active task 的 `status` / `ownerRole` 应保持一致：

| workflow phase | workflow-state.ownerRole | task.status | task.ownerRole | 语义 |
|---|---|---|---|---|
| `planning` | `planner` | `idle` | `developer` | plan package 已生成但尚未激活 task；`task.ownerRole` 表示激活后的下一接手角色。 |
| `implementing` | `developer` | `implementing` | `developer` | 开发者实现当前 task。 |
| `testing` | `tester` | `testing` | `tester` | 测试者执行 verification commands / checks。 |
| `reviewing` | `reviewer` | `reviewing` | `reviewer` | 评审者产出结构化 `review` gate 结果。 |
| `archiving` | `developer` | 无 active task；plan 内 task 均为 `done` | 保留各 task 最后责任角色 | 当前 plan 无未完成 task，`activeTaskId = null`，进入归档。 |

状态/角色写入要求：

- 任意阶段转换都必须同步刷新 `workflow-state.ownerRole`。
- `planning → implementing`：选中 task 从 `idle/developer` 变为 `implementing/developer`。
- `implementing → testing`：当前 task 变为 `testing/tester`。
- `testing → reviewing`：当前 task 变为 `reviewing/reviewer`。
- `reviewing → implementing`：当前 task 必须已有 `review.lastResult = "failed"`，再变回 `implementing/developer`，并记录评审未通过摘要。
- `reviewing` 通过后：当前 task 必须已有通过的结构化 `review` gate，才能标记为 `done`；若还有可执行 task，再按单 active task 规则激活下一 task；若没有后续 task，则进入 `archiving` 且 `activeTaskId = null`。

`handoff.md` 可以记录角色交接摘要，但不是真相源；真实状态以 `workflow-state.json` 与 `tasks.json` 为准。

### 3.2 阶段流转的脚本与工件边界

阶段流转不是只改 `workflow-state.currentPhase`。对 L2/L3 来说，每次 `planning → implementing → testing → reviewing` 都必须同时维护四类工件：

| 工件 | 职责 | 写入边界 |
|---|---|---|
| `work/workflow-state.json` | workflow 级阶段、责任角色、active task、下一步 | 只能经 `state-write.py` 写入 |
| `work/plans/active/<PLAN-ID>/tasks.json` | task 级状态、责任角色、验证结果、评审结果、阻塞原因 | 只能经 `update-task.py` 写入；不得由 Agent 临时手写状态 |
| `work/plans/active/<PLAN-ID>/handoff.md` | 阶段转换与角色交接摘要 | Agent 负责语义摘要；不得替代 state / tasks |
| `work/sessions/YYYY-MM-DD/session-<id>.md` | 命令输出、review 过程、异常分析等会话审计 | Agent 记录可复核证据 |

当前已实现的相关脚本：

- `session-start.py`：会话启动 preflight。检查 Harness 关键工件与环境，运行 `lint-harness.py`，在 `workflow-state.json` 缺失且没有 active plan 时从模板创建首个 L0/L1 state，随后运行 `validate-state.py` 并写入 `work/sessions/YYYY-MM-DD/session-<id>.md` 审计快照。它不得修改已有 state，不得激活 task，不得推进 phase。
- `materialize-tasks.py`：从已确认的 `plan.md` 任务契约生成初始 `tasks.json`，所有 task 均为 `idle/developer`，`review.lastResult = "not_run"`。
- `update-task.py`：`tasks.json` 的 task 状态写入网关。负责更新 task `status`、`ownerRole`、`currentStep`、`nextAction`、`verification`、`review`、`blockedReason`，并在写入前校验 `tasks.schema.json` 与 task 完成前置条件。
- `select-next-task.py`：只读选择器。按 `dependsOn` 与 `status` 选出下一个可执行 `idle` task；若 plan 内所有 task 均为 `done`，输出进入 `archiving` 的 state patch 建议。它只输出给 `update-task.py` / `state-write.py` 使用的结构化建议，不直接写 `tasks.json` 或 `workflow-state.json`。
- `state-write.py`：`workflow-state.json` 唯一写入网关。
- `start-workflow.py`：从 `completed` / `archived` 终态开启新的 `active` workflow。它不直接写 state，而是经 `state-write.py --allow-terminal-reset` 执行显式 terminal reset；direct L0/L1 进入 `implementing/developer`，planned L2/L3 绑定已存在 active plan package 并进入 `planning/planner`。
- `lifecycle-transaction.py`：生命周期流转事务协调器。对一次 transition 执行 `lint-harness.py` / `validate-state.py` preflight，在隔离副本里 dry-run，再调用 `update-task.py` 与 `state-write.py` 落盘并追加 `handoff.md`，最后执行 postflight。它不替代底层写入网关；当前支持 `activate-next`、`start-testing`、`start-review`、`review-failed`、`review-passed`。
- `commit-task.py`：task 完成提交 gate。只在 `lifecycle-transaction.py review-passed` 之后使用；它读取 `workflow-state.json` 与当前 active plan 的 `tasks.json`，确认目标 task 已 `done` 且 verification/review 均 passed，然后执行 `git add -A` 与 `git commit`。它不写 state/tasks，不替代 lifecycle transition。
- `archive-plan.py`：归档工具。只在 `currentPhase=archiving` 时使用；要求 Agent 已写好结构完整的 `closure.md`，并校验所有 task 均为 `done` 后迁移 active plan package，再经 `state-write.py` 收口 workflow state。
- `complete-workflow.py`：L0/L1 direct workflow 收口工具。要求 `activePlanRef=null`、`activeTaskId=null`、没有 active plan 目录，且当前 workflow 处于 `reviewing/reviewer`；调用方必须提供 verification evidence 与 review summary。脚本经 `state-write.py` 将 `workflowStatus` 置为 `completed`，并把 completion evidence 写入 session 审计 JSONL。
- `validate-state.py`：校验 workflow state 与 active task 的跨文件一致性。
- `lint-harness.py`：只读巡检目录结构与全局不变量。适合作为 session start、`planning → implementing`、active task 切换、归档前后的 preflight / postflight gate。

标准阶段流转顺序如下。凡涉及 `workflow-state.json` 的修改，最后都必须经 `state-write.py`；凡涉及 `tasks.json` 的修改，都必须经 `update-task.py`。

| 转换 | tasks.json 变化 | workflow-state.json 变化 | 其他工件 |
|---|---|---|---|
| `planning → implementing` | 选中的 `idle/developer` task 变为 `implementing/developer`，写入 task 级 `nextAction` | `currentPhase=implementing`、`ownerRole=developer`、`activeTaskId=<TASK-ID>`、刷新 workflow `nextAction` | 优先通过 `lifecycle-transaction.py activate-next` 编排，并在 `handoff.md` 追加 planner → developer 交接 |
| `implementing → testing` | 当前 task 变为 `testing/tester`；`verification.lastResult` 保持 `not_run` 或 `failed` | `currentPhase=testing`、`ownerRole=tester`、保留同一 `activeTaskId`、刷新 `nextAction` | 记录可执行验证命令或检查项 |
| `testing → reviewing` | 当前 task 需先写入 `verification.lastResult=passed`，再变为 `reviewing/reviewer` | `currentPhase=reviewing`、`ownerRole=reviewer`、保留同一 `activeTaskId`、刷新 `nextAction` | `work/sessions/...` 记录验证证据摘要 |
| `reviewing → implementing`（review failed） | 当前 task 必须已有 `review.lastResult=failed`，再回到 `implementing/developer`，保留或刷新 task 级 `nextAction` | `currentPhase=implementing`、`ownerRole=developer`、保留同一 `activeTaskId`、刷新 `nextAction` | `handoff.md` 或 session 记录 review findings 摘要 |
| `reviewing → implementing`（next task） | 当前 task 满足 done 前置条件（含结构化 review passed）后变为 `done`；下一个可执行 task 变为 `implementing/developer` | `currentPhase=implementing`、`ownerRole=developer`、`activeTaskId=<NEXT-TASK-ID>`、刷新 `nextAction` | `select-next-task.py` 只读选择下一个 task；随后必须运行 `commit-task.py --task <COMPLETED-TASK-ID>`，提交可包含下一 task 激活状态变更 |
| `reviewing → archiving` | 当前 task 满足 done 前置条件（含结构化 review passed）后变为 `done`，且 plan 内所有 task 均为 `done` | `currentPhase=archiving`、`ownerRole=developer`、`activeTaskId=null`、刷新 `nextAction` | 先运行 `commit-task.py --task <COMPLETED-TASK-ID>` 提交 task 完成结果，再由 Agent 写 `closure.md` 后交给 `archive-plan.py` |
| `reviewing → completed`（L0/L1） | 无 `tasks.json` 变化 | `workflowStatus=completed`、`activePlanRef=null`、`activeTaskId=null`、保留 `currentPhase=reviewing` / `ownerRole=reviewer` 作为最后 gate 记录、刷新 `nextAction` | `complete-workflow.py` 记录 verification evidence 与 review summary 到 session 审计 |
| terminal → new active workflow | direct L0/L1 无 `tasks.json`；planned L2/L3 要求 active plan package 已存在且通过 postflight lint | `workflowId=<NEW-ID>`、`workflowStatus=active`、显式重置 `activePlanRef` / `activeTaskId` / `currentPhase` / `ownerRole` / `nextAction` | 必须经 `start-workflow.py`，底层由 `state-write.py --allow-terminal-reset` 写入；禁止手写 state |

结构化 review gate 已落到 `tasks.schema.json`：`review.lastResult = "passed"` 只有在 `score >= threshold`、存在 `review.checks`、无 critical finding、无 blocking important finding 时才可支撑 task `done`；`minor` finding 只能作为非阻断清理项。详细 review prose 仍写入 `work/sessions/...`、`handoff.md` 或 `closure.md`，`tasks.json` 只保存 compact gate summary。

### 3.3 task 完成提交 gate

L2/L3 每个 task 在 `lifecycle-transaction.py review-passed` 成功并完成 postflight 后，必须通过 `commit-task.py --task <COMPLETED-TASK-ID>` 产生一次 task 完成提交，然后才允许开始新的实现工作或编写归档 closure。

该 gate 的位置是：

1. 先完成当前 task 的 verification 与结构化 review。
2. 运行 `lifecycle-transaction.py review-passed`，把当前 task 置为 `done`。
3. 若还有后续 task，`review-passed` 可同时激活下一个 task；若没有后续 task，则进入 `archiving`。
4. 立即运行 `commit-task.py --task <COMPLETED-TASK-ID>`。
5. 再开始下一个 task 的实现，或继续写 `closure.md` 并归档 plan。

提交可以包含 `review-passed` 产生的状态变更、`handoff.md` 追加记录、以及下一个 task 激活造成的 `workflow-state.json` / `tasks.json` 变化。这样能保证“完成当前 task”与“workflow 指向下一步”的审计状态在同一个提交中闭环。禁止在完成 task 后先做下一项实现再提交，否则提交边界会混入两个 task 的交付内容。

`commit-task.py` 的确定性检查：

- 目标 task 必须存在于当前 active plan 的 `tasks.json`。
- 目标 task 必须 `status=done`。
- `verification.lastResult` 必须为 `passed`，且必须存在 commands 或 checks。
- `review.lastResult` 必须为 `passed`，`score >= threshold`，存在 `review.checks`，且无 critical finding、无 blocking important finding。
- worktree 必须存在可提交 diff；空提交不代表 task 完成，必须阻断。

commit gate 不是独立 task，也不改变 task status。Git commit 历史是提交审计来源，`tasks.json` 不保存 commit hash。

---

## 4. 单 active task 不变量

L2/L3 在 implementing/testing/reviewing 阶段**必须有且仅有一个 activeTaskId**。

- schema 已强制"plan 驱动 + 执行阶段 ⇒ activeTaskId 是 string"。
- 规则层补充：`activeTaskId` 必须对应 tasks.json 中某条 `status ∈ {implementing, testing, reviewing}` 的任务。`idle/done/blocked` 的任务不得作为 activeTaskId。
- `workflow-state.ownerRole` 必须等于当前 active task 的 `ownerRole`。
- 切换 `activeTaskId` 必须经 `state-write.py` 网关；旧任务必须先经 `update-task.py` 落到 `done` 或 `blocked`，再切换。**禁止两个任务并发为 active**。

L0/L1 不存在 active task 不变量——`activeTaskId` 必为 null，工作单元由 `workflowId` 描述，当前责任由 `workflow-state.ownerRole` 描述。

---

## 5. activeTaskId 必为 null 的场景

汇总（schema 已部分强制，此处统一备查）：

| 场景 | activePlanRef | activeTaskId | 出处 |
|---|---|---|---|
| L0/L1 全程 | `null` | `null` | 本文 §1 / schema allOf |
| L2/L3 处于 `planning` 阶段 | active plan 路径 | `null` | schema allOf |
| L2/L3 处于 `archiving` 阶段 | active plan 路径 | `null` | schema allOf |
| `workflowStatus = completed` | `null` | `null` | schema allOf |
| `workflowStatus = archived` | `null` | `null` | schema allOf |

`activePlanRef = null` / `activeTaskId = null` 不代表无人负责；所有上述场景仍必须保留合法的 `workflow-state.ownerRole`。

---

## 6. 任务等级升降级

执行过程中发现等级判断错误时：

- **L0 → L1**：仅追加验证步骤，state 形态不变，无需迁移。
- **L1 → L2**：必须停下，进入 planning 阶段；先在 `work/plans/active/` 下生成并校验 `<PLAN-ID>/plan.md` + `tasks.json`，再经 `state-write.py` 提交 patch 设置 `activePlanRef` / `currentPhase=planning` / `ownerRole=planner`。后续 task activation 再切入 implementing。**禁止边干边补 plan**。
- **L2 → L3**：拆分当前 plan 或新增后继 plan，按 plan 顺序推进；同一时刻仍只有一个 active plan。
- **降级（L2 → L1）**：仅当 plan 与 tasks.json 尚未承载实质内容时允许；归档当前 plan 目录，state `activePlanRef` 置 null，回到 L1 形态。

升降级一律视为状态变更，必须经 `state-write.py` 落盘并写入会话审计。

---

## 7. 任务完成判定

L2/L3 task 进入 `done` 的充要条件：

1. `verification.lastResult == "passed"`。
2. `verification.commands` 与 `verification.checks` 至少有一项非空（否则视为"未定义验证"，禁止 done）。
3. `review.lastResult == "passed"`，`review.score >= review.threshold`，且无 critical finding、无 blocking important finding。
4. 所有 `dependsOn` 中的任务均为 `done`（schema 不强制；当前由 `update-task.py` 在写入 `done` 时校验，由 `select-next-task.py` 在选下一个 task 时校验候选 task 的依赖）。

L0/L1 工作流完成的判定：

1. `activePlanRef = null` 且 `activeTaskId = null`。
2. `work/plans/active/` 没有残留 active plan 目录。
3. 当前 workflow 已进入 `reviewing/reviewer` gate。
4. session 审计记录包含 verification evidence 与 review summary。
5. session 审计记录包含 architecture impact summary，说明 root `ARCHITECTURE.md` 与 Harness framework architecture 是否已更新或为何无需更新。
6. `workflowStatus` 经 `complete-workflow.py` / `state-write.py` 流转至 `completed`，`nextAction` 被替换为下一个 workflow 的初始动作。

开启下一个 workflow 的判定：

1. 当前 workflow 必须已经是 `workflowStatus ∈ {completed, archived}`。
2. 当前 state 不得持有 `activePlanRef` 或 `activeTaskId`。
3. 新 workflow 必须使用新的 `workflowId`，禁止复用旧 workflowId。
4. direct L0/L1 进入 `currentPhase=implementing`、`ownerRole=developer`、`activePlanRef=null`、`activeTaskId=null`。
5. planned L2/L3 进入 `currentPhase=planning`、`ownerRole=planner`，且 `activePlanRef` 必须指向已存在的 active plan package。
6. 写入必须通过 `start-workflow.py` 编排，并由 `state-write.py --allow-terminal-reset` 落盘。

---

## 8. nextAction 与生命周期

`nextAction` 是 schema 与本规则的交叉点：

- schema：`minLength: 1`、`maxLength: 200`。
- 规则（`validate-state.py` 启发式）：单句原子动作，禁止多步动词、禁止"优化/完善/整理"等模糊词。
- 生命周期约束：每次阶段转换必须同步刷新 `nextAction` 与 `ownerRole`。`state-write.py` 在 `nextAction` 未变化时警告状态滞后；在 patch 未显式包含 `ownerRole` 时警告责任角色交接不清晰。

---

## 9. Architecture Impact Gate

Architecture Impact 是 workflow gate，不是 standalone task。它要求 Agent 在计划、review、completion / closure 时判断本次工作是否让架构文档失真。

判断边界：

- 目标项目业务模块、依赖、数据流、运行拓扑、外部接口或项目边界变化时，检查 root `ARCHITECTURE.md` 是否需要更新。
- Harness schema、rules、scripts、templates、skills、生命周期模型或 `.harness/` 框架边界变化时，检查 `.harness/ARCHITECTURE.md` 是否需要更新。
- `work/` 下 workflow-state、plan、tasks、handoff、session 审计只属于运行态或审计证据；除非改变了生命周期规则本身，否则不构成架构文档更新理由。

写入边界：

- L2/L3 planning：`plan.md` 必须有 `Architecture Impact`，记录预期影响。
- L2/L3 task review：review checks 必须覆盖实际 Architecture Impact，发现文档失真时应作为 blocking finding，除非有明确 deferReason。
- L2/L3 archiving：`closure.md` 必须有 `Architecture Impact`，记录最终更新或不更新的理由；`archive-plan.py` 只校验章节存在，不判断语义质量。
- L0/L1 completion：`complete-workflow.py` 必须记录 architecture impact summary 到 session completion audit。

只有当更新架构文档本身是具体交付产物时，才允许把它建成 task；禁止创建只用于“判断是否需要更新架构”的流程 task。

---

## 10. 与 handoff、archive 的衔接

- 阶段转换、活跃任务切换、等级升降级 —— 三者必须在 `handoff.md` 中追加一条记录；记录格式见 `.harness/rules/handoff-rules.md`。
- `session-start.py` 写入的 session 文件只作为会话启动证据与 Agent 语义记录容器；它不是 workflow 或 task 真相源，不得用于替代 `workflow-state.nextAction`、`tasks.json` 或 `handoff.md`。
- `archiving → archived` 的最后一步应先由 Agent 写 `closure.md`，再由 `archive-plan.py` 迁移 `plans/active/<PLAN-ID>/` 到 `plans/archived/<PLAN-ID>/` 并经 `state-write.py` 将 `workflowStatus` 置为 `archived`。
- L0/L1 无 plan，跳过 plan 迁移与 `closure.md`，通过 `complete-workflow.py` 将 workflow 收到 `completed`，并在 session 审计 JSONL 中记录 verification evidence、review summary 与 architecture impact summary。
- `completed` / `archived` 不是继续执行的 phase；下一项工作必须经 `start-workflow.py` 创建新的 workflowId 后再推进。

---

## 11. 违规处理速查

| 违规 | 触发位置 | 处理方式 |
|---|---|---|
| L0/L1 形态下 `activeTaskId` 非 null | `validate-state.py` 跨文件层 | 阻断；提示置为 null |
| `activePlanRef` 指向的 `plan.md` 或同目录 `tasks.json` 不存在 | `validate-state.py` 跨文件层 | 阻断；要求先 materialize 完整 plan package |
| L2/L3 执行阶段 `activeTaskId` 不在 tasks.json | `validate-state.py` 跨文件层 | 阻断；要求修正或重新选任务 |
| `currentPhase` 跳跃式转换 | `state-write.py` lifecycle 层 | 阻断；要求经合法路径 |
| `reviewing → archiving` 时 active task 未 `done` 或 plan 仍有未完成 task | `state-write.py` lifecycle 前置条件 | 阻断；先经 `update-task.py` / `lifecycle-transaction.py review-passed` 完成结构化 review gate |
| `currentPhase` 与 `workflow-state.ownerRole` 不匹配 | schema | 阻断；按 phase 修正 ownerRole |
| L2/L3 active task 的 `ownerRole` 与 `workflow-state.ownerRole` 不一致 | `validate-state.py` 跨文件层 | 阻断；同步 workflow 与 task 责任角色 |
| 双 active task | `select-next-task.py` + `state-write.py` + `lint-harness.py` | 选择器拒绝在已有 active task 时选择新 task；写入网关拒收不一致 state；目录/任务巡检由 lint 固化 |
| `plans/active/` 残留目录但 `activePlanRef = null` | `lint-harness.py` | 阻断；要求归档或恢复引用 |
| L0/L1 completion 被用于 plan-backed workflow | `complete-workflow.py` | 阻断；要求改走 `archive-plan.py` |
| 从非终态开启新 workflow | `start-workflow.py` | 阻断；要求先完成或归档当前 workflow |
| terminal reset 复用旧 workflowId 或未显式清空 active 引用 | `state-write.py --allow-terminal-reset` | 阻断；要求使用新 workflowId 并显式写入完整 state 字段 |
