# T-068 Developer Verification — 2026-08-09

## Scope

- 生成任务完成后的人工确认门禁。
- 文章发布页三类发布队列。
- 单篇直发与多选批量发布。
- 发布结果重试后的正确归类。

## Implemented

- `content_generation_tasks` 新增可回滚的 `confirmed_at` 字段与 0029 数据库迁移。
- 新增任务确认接口；只有全部文章已经生成且达到可发布状态时才能确认。
- 批量生成文章在任务确认前不能调用发布接口，避免半成品进入发布流程。
- 文章 DTO 返回生成任务和确认时间，发布页仅接收已经确认且仍通过质量门禁的文章。
- 发布页删除内容状态筛选、发布状态筛选、已删除入口以及列表中的编辑、复制、删除操作。
- 发布页改为“未发布、已发布、发布失败”三类互斥视图。
- 未发布和发布失败视图支持单选、全选和批量发布；单篇与批量发布共用目标平台账号解析与结果轮询。
- 单篇“发布”会自动使用文章指定平台下全部已连接、已启用且尚未成功提交的账号。
- 同一文章、版本、账号重试成功后，旧失败记录不再覆盖最新成功状态。
- 内容工作台任务详情新增“确认内容，进入发布”；生成未完成或存在未达标文章时按钮保持禁用。

## Developer Checks

- Backend targeted integration and contract tests:
  - `3 passed`：生成任务确认、发布前确认门禁、发布账号预检、OpenAPI 合同。
- Backend static checks:
  - Ruff check passed。
  - Ruff format check passed。
  - Mypy passed。
- Frontend checks:
  - Prettier passed。
  - ESLint passed。
  - Vue TypeScript check passed。
  - Vitest `14 files / 79 tests passed`。
  - Vite production build passed。
- Database:
  - PostgreSQL migrated from `0028` to `0029 (head)`。
- Runtime:
  - API and worker restarted。
  - readiness reports database, storage and worker heartbeat all `ok`。
- Browser regression:
  - Verified task confirmation control exists and stays disabled while a task is generating。
  - Verified tabs are `未发布 / 已发布 / 发布失败`。
  - Verified content/publication state filters and deleted tab are absent。
  - Verified all expected table columns remain visible at the active desktop viewport。
  - Verified a clean publishing page load has no console errors。
  - Real publication was intentionally not triggered during UI regression。

## Status

Developer verification complete. Task remains `in_progress`; independent Tester and product acceptance are not self-approved by Developer.
