# 整体架构
```Plain text
repo/
├─ AGENTS.md
├─ README.md
├─ architecture/
│  └─ architecture.md
│
├─ work/
│  ├─ workflow-state.json
│  ├─ workflow/
│  │  ├─ session-start.md
│  │  ├─ task-lifecycle.md
│  │  ├─ handoff-rules.md
│  │  └─ archive-rules.md
│  │
│  ├─ plans/
│  │  ├─ active/
│  │  │  └─ PLAN-001/
│  │  │     ├─ plan.md
│  │  │     ├─ tasks.json
│  │  │     └─ handoff.md
│  │  │
│  │  └─ templates/
│  │     ├─ plan.template.md
│  │     ├─ tasks.template.json
│  │     └─ handoff.template.md
│  │
│  └─ archive/
│     └─ plans/
│        └─ PLAN-001/
│           ├─ plan.md
│           ├─ tasks.json
│           ├─ handoff.md
│           └─ closure.md
│
├─ scripts/
│  ├─ scripts.md
│  ├─ check-env.sh
│  ├─ session-start.sh
│  ├─ validate-state.py
│  ├─ select-next-task.py
│  ├─ sync-plan-to-state.py
│  ├─ archive-plan.py
│  └─ lint-harness.py
│
└─ src/
```

## 架构详细说明
- `AGENTS.md`: harness入口文档，作为该项目仓库的唯一入口和事实来源，包含了所有关于harness的核心信息和目录导航.
- README.md: 项目readme，主要面向人类读者，提供项目概览、安装指南、使用说明等内容。
- scripts/: 存放各种脚本文件，用于自动化任务和工作流管理。
  - session-start.sh: 会话启动脚本，它的作用如下：1.确保harness必要目录和文件都存在；2. 检查。
  - archive-task.sh: 归档任务脚本，用于将完成的任务归档以便后续参考和审计。