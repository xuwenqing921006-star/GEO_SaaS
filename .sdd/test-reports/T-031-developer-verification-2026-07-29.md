# T-031 Developer Verification — 2026-07-29

## 范围

- 独立模型复核返回格式兼容。
- 单篇与批量重新质检前端闭环。
- 重新质检不改写文章版本并保留发布状态。
- 本地运行进程和内容工作台页面冒烟检查。

## 自动化结果

- `uv run --project backend ruff check backend/app/content.py backend/tests/content/test_content_api.py`
  通过。
- `uv run --project backend mypy backend/app/content.py` 通过。
- 内容后端定向回归：32 项通过。
- 前端 ESLint、类型检查、全量单元测试和生产构建通过。
- 前端全量单元测试：8 个文件、59 项通过。
- 重新质检逻辑定向单元测试：8 项通过。
- `node ../../scripts/ecc-v2.js doctor` 通过。

## 页面与运行验证

- 本地 API `http://127.0.0.1:8000/api/v1/health/ready` 返回：
  database、storage、worker heartbeat 全部正常。
- 内容工作台展示：
  - `重新质检待修正文章（19）`
  - 每篇文章的 `重新质检`
  - 文章详情中的 `重新质检`
- 批量按钮采用明亮蓝色次级按钮样式，当前页面布局无明显溢出。
- 页面验证没有点击重新质检按钮，没有产生真实模型用量。

## 关键断言

- 常见 DeepSeek、千问复核 JSON 变体可解析。
- 缺少问题列表的未知结构仍返回模型格式异常。
- 重新质检后文章版本 ID、正文和版本数量不变，质量检查数量增加一条。
- 已发布的当前版本重新质检后继续保持发布状态。

## 状态说明

本报告仅记录 Developer 自验结果。根据项目门禁，任务仍保持 `in_progress`，
等待独立 Tester 验证和 Product Manager 业务验收。
