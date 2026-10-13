# 开发就绪门禁：新项目运行基线解释

日期：2026-07-27  
状态：Accepted

## 背景

Development Readiness Gate 同时要求：

- 先通过门禁，才能搭建生产代码；
- 具有 Plan、tasks、working runtime 和 baseline commands。

本项目是新产品，阶段 C 完成时没有生产脚手架。若将 working runtime 解释为“项目脚本已经存在并运行”，就必须在门禁前搭建生产代码，与新产品工作流冲突。

## 决定

对全新项目：

- `working runtime` 指目标运行工具已经在开发机可用；
- `baseline commands` 指 Plan 与首个任务已经定义将创建和验证的项目命令；
- `.sdd/tasks.json` 是门禁输入，不是生产代码，可以在门禁前由 Planner 创建；
- 生产脚手架由门禁通过后的 T-001 创建。

## 当前证据

- 用户已明确说“开始开发”。
- Node.js `24.14.0`、pnpm `10.33.0`、uv `0.11.30` 可用。
- uv 管理的 Python `3.13.14` 可用。
- Docker `29.5.2` 与 Docker Compose `5.1.4` 可用。
- `docs/Plan.md` 已定义前端 format/lint/type/unit/build、后端 format/lint/type/test、数据库迁移、健康检查和 Compose 验证。

## 结果

Planner 可以先生成任务；Development Gate 通过后，T-001 才能创建前后端、数据库和测试脚手架。该解释不允许在门禁前写生产代码。
