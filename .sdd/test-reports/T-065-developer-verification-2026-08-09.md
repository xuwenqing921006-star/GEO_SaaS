# T-065 开发侧验证记录

日期：2026-08-09  
结论：实现与开发侧验证完成，等待独立 Tester 验收；本记录不将任务自行标记为通过。

## 实现范围

- 关键词页移除“用已选关键词生成内容”和“生成内容（数量）”两个入口。
- 内容工作台移除“AI 生成文章”标题说明头、管理关键词入口、关键词搜索和类型筛选。
- 关键词列表增加全选/取消全选；当正式关键词超过上限时选择前 20 个，与生成接口限制一致。
- 内容工作台直接选择正式关键词，并在同一页面配置平台类型、已连接自媒体平台、每平台篇数、文章长度和多个内容形式。
- 首版仅开放自媒体；官媒、自媒体大 V 作为不可选的后续能力展示。
- 未配置、未连接或未启用发布账号的平台不可选。
- 总篇数固定为“已选平台数 × 每个平台篇数”，不乘关键词数量。
- 多种内容形式在每个平台内轮换分配。
- 新增持久化内容生成任务、任务列表、任务详情和任务关联文章。
- 保留原文章查看、编辑、复制、质量状态和发布流程。

## 数据库与接口

- 新增迁移 `0028_content_generation_tasks.py`，创建内容生成任务表并为文章增加可空任务外键；包含 downgrade。
- 新增任务列表与任务详情接口。
- 批量生成接口增加平台类型、内容形式集合和任务快照响应。
- OpenAPI 合同路由基线由 89 更新为 91。
- 本地业务数据库已升级至 `0028 (head)`；未删除客户、知识库、文章或发布记录。

## 自动化验证

| 范围 | 命令/检查 | 结果 |
| --- | --- | --- |
| 新任务后端集成 | `uv run pytest tests/content/test_content_generation_tasks.py -q` | 1 passed |
| OpenAPI 与新任务 | `uv run pytest tests/test_openapi_contract.py tests/content/test_content_generation_tasks.py -q` | 2 passed |
| 内容后端回归 | `uv run pytest tests/content/test_content_api.py -q` | 66 passed |
| 后端静态检查 | `uv run ruff check ...` | passed |
| 后端类型检查 | `uv run mypy app/content.py app/database.py app/contract_models.py app/main.py` | passed |
| 前端全量单测 | `npm run test:unit -- --run` | 13 files / 75 tests passed |
| 前端 Lint | `npm run lint` | passed |
| 前端类型检查 | `npm run typecheck` | passed |
| 前端生产构建 | `npm run build` | passed |
| 关键词全选定向单测 | `npm run test:unit -- --run tests/content-workbench-logic.spec.ts` | 11 passed |
| 本地服务健康 | API `/health/live`、Web `:5173` | HTTP 200 / HTTP 200 |

## 浏览器验收

- 使用现有莱恩美术客户数据进入内容工作台，不执行真实付费生成。
- 选择 1 个正式关键词、搜狐号、2 种内容形式，每平台篇数为 1 后，“开始 AI 生成”按钮可用，页面显示“预计生成 1 篇”。
- 平台卡片正确区分：搜狐号、百家号可选；头条号未连接或未启用不可选；网易号未配置不可选。
- 关键词页的两个旧内容生成按钮均不存在，正式关键词库和内容工作台提示仍可见。
- 内容工作台不再显示“AI 生成文章”标题头、管理关键词按钮、搜索框或类型筛选。
- 本地 58 个正式关键词场景中，全选后选中 20 个并切换为“取消全选”，再次点击恢复 0 个；“已选 0”徽标无截断。
- 页面无控制台错误；没有改动已有 6 篇文章。

## 待独立验收

- 独立 Tester 创建一个最小生成任务，验证真实异步任务状态、任务详情和文章编辑。
- 独立 Tester 复核数据库迁移 downgrade/upgrade、并发重复提交边界和跨客户 404。
- 产品侧确认工作台字段和任务列表信息密度。
