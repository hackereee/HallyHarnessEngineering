# Harness Engineering workflow

## session-start.py
### 1.Harness检查:
- 整个Harness目录与文档是否完备? 完备 - 继续， 不完备 - 补全所有的目录与文档
- 检查所有Harness脚本是否完备? 不完备 - 报错返回大模型，不允许继续执行
- 检查开发环境: 构建cli,单元测试cli 等等, 不强控, 返回错误信息给大模型决策能否正常安装
### 2. validate-state.py
1. 检查 workflow-state.json 状态
