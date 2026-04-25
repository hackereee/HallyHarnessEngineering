# workflow-lifecycle.md

`workflow-state.json` 的流转规则与语义约定。**只写 schema 无法表达的内容**——结构、枚举、跨字段约束已落到 `workflow-state.schema.json` / `tasks.schema.json`，本文不重复。

涵盖：任务等级 ↔ state 形态映射、workflow 粒度、阶段转换、单活跃任务不变量、等级升降级、与 handoff/archive 的衔接。

定位：`.harness/rules/` 规则层文档。配套 schema、`task-level.md`、`validate-state.py` 共同约束任务从创建到归档的全过程。

---

## 1. 任务等级 ↔ state 形态映射

任务等级定义见 `task-level.md`。等级直接决定 `workflow-state.json` 的合法形态：

| 等级 | 触发条件 | activePlanRef | activeTaskId | 审计锚点 | plan.md / tasks.json |
|---|---|---|---|---|---|
| L0 / direct-patch | 局部、低风险、无需正式规划 | `null` | `null` | `workflowId` | 不创建 |
| L1 / verified-fix | 范围有限的修复，需定向验证 | `null` | `null` | `workflowId` | 不创建 |
| L2 / planned-task | 需先规划再执行 | `./plans/active/<PLAN-ID>/plan.md` | `tasks.json` 中某条 taskId | `activeTaskId` | 必须创建 |
| L3 / decomposed-epic | 须拆为多子任务或阶段性 plan | 同上（每段独立 plan） | 同上 | `activeTaskId` | 必须创建，可能多份顺序推进 |

**不变量**：
- L0/L1 期间 `work/plans/active/` 必须为空。残留即视为状态不一致，由 `lint-harness.py` 巡检。
- L2/L3 期间 `activePlanRef` 指向的 plan 目录必须存在 `plan.md` 与 `tasks.json`。

---

## 2. workflow 粒度

工作流是**任务级**容器：一个 workflow 对应一次完整的"接需求 → 执行 → 归档"。

- `workflowId` 创建后不变，命名应携带任务语义，便于审计追溯。
  - L0/L1 推荐：`workflow-fix-<slug>-<yyyymmdd>-v1`、`workflow-adhoc-<yyyymmdd>-NNN`
  - L2/L3 推荐：`workflow-plan-<NNN>-v1`
- 一个 workflow 完成后必须流转至 `completed` 或 `archived`，再开下一个。**禁止复用 workflowId 承接新需求**。
- 同一时刻 `work/workflow-state.json` 只承载一个 workflow 的运行态。

---

## 3. 阶段转换

`currentPhase` 的合法转换图（schema 只校验枚举与单点跨字段约束，转换路径属规则层）：

```
planning ──► implementing ──► testing ──► reviewing ──► archiving
   ▲             │                                          │
   │             └─► (回退) planning  (仅在范围重定义时)     │
   └──────────────────── (新 workflow) ◄─────────────────────┘
```

**转换前置条件**：

| 转换 | 前置 |
|---|---|
| `planning → implementing` | L2/L3：`plan.md` + `tasks.json` 已落盘且 schema 校验通过；`activeTaskId` 已选定。L0/L1：跳过 planning，启动即 implementing。|
| `implementing → testing` | 当前 task 的实现产物已具备可验证形态（命令/检查项可跑）。|
| `testing → reviewing` | `verification.lastResult == "passed"`。|
| `reviewing → archiving` | 评审通过；L2/L3 的 plan 已无未完成 task。|
| `archiving → (终态)` | `archive-plan.py` 完成迁移；workflowStatus 置为 `completed` 或 `archived`。|

**禁止跳跃**：例如 `planning → testing` 直接跳过 implementing 是非法的，由 `validate-state.py` 的语义层检查（schema 不强制）。

**回退**：仅允许 `implementing → planning`，且必须伴随 plan/tasks 的范围调整记录（写入 handoff）。其他回退一律视为非法。

---

## 4. 单 active task 不变量

L2/L3 在 implementing/testing/reviewing 阶段**必须有且仅有一个 activeTaskId**。

- schema 已强制"plan 驱动 + 执行阶段 ⇒ activeTaskId 是 string"。
- 规则层补充：`activeTaskId` 必须对应 tasks.json 中某条 `status ∈ {implementing, testing}` 的任务。`idle/done/blocked` 的任务不得作为 activeTaskId。
- 切换 activeTaskId 必须经 `state-write.py` 网关；旧任务先落到 `done` 或 `blocked`，再切换。**禁止两个任务并发为 active**。

L0/L1 不存在此不变量——activeTaskId 必为 null，工作单元由 `nextAction` + `workflowId` 描述。

---

## 5. activeTaskId 必为 null 的场景

汇总（schema 已部分强制，此处统一备查）：

| 场景 | 必为 null | 出处 |
|---|---|---|
| L0/L1 全程 | ✓ | 本文 §1 |
| L2/L3 处于 `planning` 阶段 | ✓ | schema allOf |
| L2/L3 处于 `archiving` 阶段 | ✓ | schema allOf |
| `workflowStatus ∈ {completed, archived}` | ✓ | schema allOf |

---

## 6. 任务等级升降级

执行过程中发现等级判断错误时：

- **L0 → L1**：仅追加验证步骤，state 形态不变，无需迁移。
- **L1 → L2**：必须停下，进入 planning 阶段；`state-write.py` 提交 patch 设置 `activePlanRef`，并在 `work/plans/active/` 下生成 `<PLAN-ID>/plan.md` + `tasks.json`，再选 `activeTaskId` 切回 implementing。**禁止边干边补 plan**。
- **L2 → L3**：拆分当前 plan 或新增后继 plan，按 plan 顺序推进；同一时刻仍只有一个 active plan。
- **降级（L2 → L1）**：仅当 plan 与 tasks.json 尚未承载实质内容时允许；归档当前 plan 目录，state `activePlanRef` 置 null，回到 L1 形态。

升降级一律视为状态变更，必须经 `state-write.py` 落盘并写入会话审计。

---

## 7. 任务完成判定

L2/L3 task 进入 `done` 的充要条件：

1. `verification.lastResult == "passed"`。
2. `verification.commands` 与 `verification.checks` 至少有一项非空（否则视为"未定义验证"，禁止 done）。
3. 所有 `dependsOn` 中的任务均为 `done`（schema 不强制，由 `select-next-task.py` / `validate-state.py` 在选任务时校验）。

L0/L1 工作流完成的判定：`nextAction` 已为空或被替换为下一个 workflow 的初始动作；同时 workflowStatus 流转至 `completed`。

---

## 8. nextAction 与生命周期

`nextAction` 是 schema 与本规则的交叉点：

- schema：`minLength: 1`、`maxLength: 200`。
- 规则（`validate-state.py` 启发式）：单句原子动作，禁止多步动词、禁止"优化/完善/整理"等模糊词。
- 生命周期约束：每次阶段转换必须同步刷新 `nextAction`，否则视为"状态滞后"。`state-write.py` 在 patch 不含 `nextAction` 字段时应警告。

---

## 9. 与 handoff、archive 的衔接

- 阶段转换、活跃任务切换、等级升降级 —— 三者必须在 `handoff.md` 中追加一条记录（详见 `handoff-rules.md`）。
- `archiving → completed/archived` 的最后一步由 `archive-plan.py` 执行：迁移 `plans/active/<PLAN-ID>/` 到 `plans/archived/<PLAN-ID>/`，生成 `closure.md`。L0/L1 无 plan，跳过迁移，仅写 closure 到 `work/sessions/` 下当日记录。

---

## 10. 违规处理速查

| 违规 | 触发位置 | 处理方式 |
|---|---|---|
| L0/L1 形态下 `activeTaskId` 非 null | `validate-state.py` 跨文件层 | 阻断；提示置为 null |
| L2/L3 执行阶段 `activeTaskId` 不在 tasks.json | `validate-state.py` 跨文件层 | 阻断；要求修正或重新选任务 |
| `currentPhase` 跳跃式转换 | `validate-state.py` 语义层 | 阻断；要求经合法路径 |
| 双 active task | `lint-harness.py` + `state-write.py` | 写入网关拒收 patch |
| `plans/active/` 残留目录但 `activePlanRef = null` | `lint-harness.py` | 阻断；要求归档或恢复引用 |
