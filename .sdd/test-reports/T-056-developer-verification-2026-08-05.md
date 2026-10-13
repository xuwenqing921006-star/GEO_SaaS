# T-056 Developer Verification — 2026-08-05

## Scope

- 将任务状态查询统一为 3/5/10 秒分阶段退避，发布任务使用 5/10/15 秒退避。
- GEO 诊断最长等待 5 分钟；关键词、文章重写与质检最长 10 分钟；监测最长 15 分钟；发布最长 10 分钟。
- 新增全局成功、失败、提示和警告通知；查询刷新失败采用去重通知。
- 内容工作台显式跟踪任务期间暂停文章列表轮询；生成中列表改为 5 秒，审核中保持 60 秒。
- 知识库解析改为 5 秒，渠道账号状态改为 5 分钟；关闭窗口聚焦自动刷新并设置 30 秒缓存。

## Developer checks

- `pnpm typecheck`：通过。
- `pnpm lint`：通过。
- `pnpm test:unit`：通过，12 个测试文件、72 个测试。
- `pnpm build`：通过。
- 修改文件定向 `prettier --check`：通过。
- 本地 `/diagnostics` 只读页面验收：页面正常加载，浏览器控制台错误为 0。

## Known baseline

- 全仓库 `pnpm format:check` 仍报告既有 `src/api/dto.ts` 格式差异；本任务未修改该文件，也未为通过检查而改写无关代码。

## Remaining gate

- 本报告只记录 Developer 自检，不标记任务 PASS。
- 仍需独立 Tester 验证轮询请求数量、超时提示和页面切换后的通知行为，并由 Product Owner 完成业务验收。
