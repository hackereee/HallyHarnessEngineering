# Learn Harness Engineering

这是一个用于学习和演进 Harness Engineering 工程标准的仓库。核心目标是把 Agent 工作流拆成可审计、可恢复、可验证的工程工件：规则由文档说明，结构由 schema 约束，状态写入由脚本网关控制，运行态数据集中落在 `work/`。

## 入口

- `AGENTS.md`：Agent 入口与事实来源。进入仓库后先读它，再按其中的读取顺序核对规则、schema、脚本和测试。
- `harness-design/architecture.md`：目录分层、关键文件职责与核心不变量。
- `.harness/rules/workflow-lifecycle.md`：workflow-state、task status、ownerRole、phase 的生命周期语义。

## 目录边界

- `.harness/` 只保存契约、模板、规则、技能、脚本和测试。
- `work/` 保存运行态数据，例如 `workflow-state.json`、active/archived plan package、session 审计记录。
- `harness-design/` 和 `learning-notes/` 保存设计说明与学习笔记，不作为运行态真相源。

## 常用验证

```bash
python3 .harness/scripts/lint-harness.py --root .
python3 .harness/scripts/validate-state.py --state work/workflow-state.json --schema .harness/schemas/workflow-state.schema.json
python3 -m unittest discover -s .harness/tests -p 'test_*.py'
```

常规 CLI 入口也可以通过：

```bash
python3 .harness/scripts/harness lint
python3 .harness/scripts/harness validate-state
python3 .harness/scripts/harness start-workflow --level L1 --workflow-id workflow-adhoc-20260427-002 --next-action 判断当前需求的任务等级
```
