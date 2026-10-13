# T-073 开发侧交接整理验证

- 日期：2026-10-13。
- 范围：文档、工具入口、Git 配置、环境示例、可选开发数据库端口覆盖层；无业务功能开发。
- 交接结论：准备交给独立 Reviewer 和 Tester。本报告不标记业务功能或任务 PASS。

## 实际变更

- AGENTS、CLAUDE、Cursor 改为普通项目约定，无原作者绝对路径或外部 Router 强制入口。
- 移除本机 `.ecc-v2.json` 与旧 Cursor 规则，原文件保留在被忽略的本地备份。
- 新增 README、`docs/handoff/HANDOFF.md` 和从原始任务逐项生成的 `OPEN-TASKS.md`。
- 增补 Git 忽略与换行规则，保留环境示例，排除环境实值、日志、备份、数据、会话与临时结果。
- 新增后端/前端环境示例和显式选用的 `compose.dev.yaml`；现有 Compose、源码、测试、迁移与锁文件保持原字节。
- 初始化本地 main 独立 Git 仓库，无暂存、提交、远程或推送。

## 验证证据

- 开发守卫：按原流程对 T-073 的范围准备通过，先于上述配置写入。此过渡记录不要求同事使用原流程。
- `node --test scripts/workspace.test.mjs`：4/4 通过。
- `docker compose -p geo-saas-handoff-check --env-file .env.example config --quiet`：解析通过。
- 同命令增加 `-f compose.yaml -f compose.dev.yaml`：解析通过。
- 生产占位样例与 `compose.production.yaml` 的 `config --quiet`：解析通过；未部署。
- 251 个业务工程文件 SHA-256 不变；原 65 个任务对象逐字段不变。
- 未完成业务任务 39 项全部覆盖，38 进行中、1 失败；登记的历史证据文件全部存在。
- 新入口与交接文档中的 62 个本地 Markdown 链接目标存在；39 个任务锚点与原任务一一对应。
- README 的原 14 个 PowerShell 代码块通过 AST 语法解析；后端示例能被实际 Settings/MigrationSettings 读取，运行/迁移角色不同、端口一致。
- Git 根路径为本项目、分支 main；index 为空、HEAD 不存在、remote 为空；11 类私有/生成文件被忽略，7 个交接必要样例或状态文件未被忽略。
- 当前监听 5173/8000/55432 仍存在；未运行重启、迁移或数据写入。
- 只读就绪检查返回 ready，数据库、文件存储和 Worker 心跳均为 ok。
- 对候选文件匹配本机环境中的长凭据及有限常见密钥格式，无命中；见 `.sdd/evidence/T-073-candidate-secret-check.json`。不代表历史客户资料和截图已全部脱敏。

可复核的摘要：`.sdd/evidence/T-073-handoff-checks.json`。业务原始哈希：`.sdd/evidence/T-073-business-baseline.json`。实际修改差异（本机、Git 忽略）：`.sdd/temp/T-073-change.diff`。原任务、状态和入口文件：`.sdd/temp/T-073-before/`。

## 限制

- 未运行全量业务测试、覆盖率、E2E、真实模型或平台发布；文档整理不表示历史任务已通过。
- 未从空库完整启动新容器环境，只验证现有结构与 Compose 静态解析；不将解析结果当作完整启动证据。
- 501 个当前候选文件中没有超过 10 MiB 的文件；候选历史文档仍需要在实际上传前做内容与敏感信息审查。
- README 将旧本机脚本和 Docker 桌面浏览器能力明确标为限制，没有通过改业务配置解决这些旧问题。

## Reviewer 反馈修正

- 原前端样例把 VITE_API_PROXY_TARGET 放入 `.env.local`，但实际 `vite.config.ts` 只读取进程环境；默认 8000 可运行，自定义值不会生效。
- 已删除样例中的无效变量，并把 README 与交接说明改为启动终端设置代理变量；Vite 配置保持原字节。
- 新增一个 PowerShell 示例。只重新核验受影响文档的语法、链接和差异；配置解析、结构与业务哈希证据不因该文档修正扩展到全量业务回归。
