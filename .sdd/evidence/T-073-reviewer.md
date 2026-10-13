# T-073 独立 Reviewer 审查

- 日期：2026-10-13。
- 范围：普通独立项目交接；入口文档、工具规则、Git 忽略/换行、环境示例与可选开发 Compose 覆盖层。
- 角色：仅审查并记录证据，不修改实现或任务状态，不代替 Tester 判定任务 PASS。
- 结论：无剩余阻断项。首轮发现 1 项 P2 交接配置说明问题，开发方已修正并经本 Reviewer 聚焦复核关闭。未发现业务文件变更、当前入口强制 ECC 依赖或 Git 远程/推送配置。本结论不替代 Tester 验证。

## 审查输入与版本

- 已读取 `harness-core/agents/reviewer.md`、当前 `AGENTS.md`、[变更计划](../changes/T-073-independent-handoff-plan.md)。
- 实际差异：`.sdd/temp/T-073-change.diff`，覆盖 13 个入口、文档和开发配置路径。
- 开发证据：[开发验证](../test-reports/T-073-developer-verification-2026-10-13.md)、[检查摘要](T-073-handoff-checks.json)、[业务文件原始哈希](T-073-business-baseline.json)。
- 另收到开发侧补充：原 14 个 README PowerShell 代码块语法解析无错误，样例可被实际 Settings/MigrationSettings 读取，有限凭据匹配无命中。反馈修正后共 15 个代码块重新通过语法解析；开发验证报告已增加反馈修正说明，实际差异已刷新。这些证据未被扩大解释为完整空库启动或全部内容脱敏。

## 已修正并复核关闭的发现

### R-01 / P2 / 已关闭：前端样例中的代理地址不会通过 `.env.local` 生效

- 首轮位置：`frontend/.env.example:3`、`docs/handoff/HANDOFF.md:60`；相关既有配置为 `frontend/vite.config.ts:10`。
- 首轮证据：新样例包含 `VITE_API_PROXY_TARGET=http://127.0.0.1:8000`，交接配置表把 `frontend/.env.local` 描述为 Vite 的 API/Mock 切换及代理地址设置。既有 Vite 配置直接读取 `process.env.VITE_API_PROXY_TARGET`；没有 `loadEnv()`。已安装 Vite 的 `dist/node/chunks/node.js:35617` 先加载配置，`:35732` 才读取 env 文件，而 `:5695-5699` 将文件中的 `VITE_*` 放入返回对象，不写入 `process.env`。
- 影响：默认 8000 路径可工作，但接手者按样例在 `.env.local` 更改 API 代理端口/地址后，前端仍代理到 8000，容易出现连不上后端或访问错误服务的情况。
- 建议：本任务保持既有业务配置不变，删除或明确注释样例中的无效代理字段；在 README 写明非默认代理地址必须在启动 Vite 的同一终端设置 `$env:VITE_API_PROXY_TARGET='http://127.0.0.1:<端口>'`，并相应调整交接配置表。`VITE_USE_MOCK` 作为前端 env 文件变量可以继续保留。
- 核验方式：基于实际配置与已安装 Vite 源码静态核对，没有启动新的服务、改环境文件或运行全量测试。
- 修正与关闭证据：`frontend/.env.example` 已移除代理变量并注明非默认地址从启动终端设置；README 第 152—159 行提供同终端设置变量、启动前端与恢复默认步骤；HANDOFF 第 60—61 行将 env 文件切换与进程代理变量分开说明。刷新后的实际差异包含上述修正，`frontend/vite.config.ts` 的 SHA-256 仍与原始业务基线一致。问题已关闭，无需修改业务代码。

## 其他审查结论与证据

- 工具独立：AGENTS、CLAUDE 和新 Cursor 规则不含外部 Router/guard 强制入口；`.ecc-v2.json` 与旧 Cursor 自动规则在实际差异中删除。OPEN-TASKS 中两条 doctor 要求明确归属于保留的历史检查条件，清单第 67 行说明它们不是继续使用原工具的要求。
- 命令对应：README 中 Node/pnpm/Python 版本、依赖安装、API/Worker 入口、迁移和负责人初始化命令与 `package.json`、`backend/pyproject.toml`、`backend/migrations/env.py`、`backend/app/bootstrap_owner.py` 对应。容器 API 自动迁移、Web 代理、负责人最小长度和禁止覆盖旧账号均有代码依据。
- 新环境配置：原生样例使用 127.0.0.1:55432、独立运行/迁移角色和 `./data`，与开发覆盖层及后端从 `backend/` 读取 `.env` 的方式一致。文档要求同步主密钥、存储和数据库凭据，说明基础 Compose 未映射发布模式且容器不提供桌面浏览器。开发覆盖层仅绑定 127.0.0.1 的数据库端口。
- 任务真实性：原始任务为 65 项（26 passed、38 in_progress、1 failed）；当前历史 65 个对象逐字段不变。清单 39 个逐项标题 ID 与全部未通过的原任务一致，标题、描述、验收条件及检查要求无缺项。T-063 历史失败与后续开发侧修复被区分；T-072 一点号最终提交保护有当前代码依据。
- 测试描述：根脚本命令均存在；主 E2E 使用临时 SQLite、fixed_mock、8003/5174 和 `reuseExistingServer: false`，不复用本机业务服务。覆盖率 75% 全后端语句/85% 指定核心模块分支与实际脚本一致。未将跳过 PostgreSQL 专项视为通过。
- 业务边界：对业务原始 SHA-256 清单进行只读复核，251 个路径全部一致。原业务任务没有被批量标为通过。
- Git 状态：当前项目是独立根目录，分支 main，index 为空，HEAD 尚不存在，`git remote -v` 无输出。可据此确认本次没有建立提交或远程配置；这些当前状态检查不被解释为远端活动的历史审计。忽略规则保留必要样例和资料，排除真实 env、存储、会话、备份及临时目录；文档明确未来上传前仍需审查历史资料。

## 本轮附加检查及理由

遵循 Reviewer 的小范围审查规则，未重复完整构建、测试套件或 Compose 检查。附加检查均为只读：

1. 触发：确认 Developer 证据属于当前工程，且业务/状态未被后续更改。操作：读取 `T-073-business-baseline.json`，对所列文件执行 `Get-FileHash -Algorithm SHA256`；将原始与当前历史任务转为相同深度 JSON 比对。结果：251 个业务文件无差异，原 65 个任务对象相同。
2. 触发：确认清单完整且忠实保留原要求。操作：解析原任务状态和 `OPEN-TASKS.md` 的 39 个 `### T-xxx` 段落，逐项比较标题、描述、验收条件和检查要求。结果：ID 无差异、字段遗漏 0。
3. 触发：确认无强制外部入口及未上传边界。操作：在 AGENTS、CLAUDE、README、Cursor、交接文档和工程入口脚本中做有界 `rg` 检索，读取 `git status --short`、`git remote -v`、`git rev-parse --show-toplevel`、`git ls-files --stage`、`git symbolic-ref --short HEAD` 和 `git rev-parse --verify HEAD`。结果：仅历史/无需安装说明中出现 ECC；独立根/main/index 空/remote 空，HEAD 验证按无提交状态返回预期失败。
4. 触发：发现前端新 env 样例与实际代理读取方式不一致。操作：精确读取 `frontend/vite.config.ts` 和已安装 Vite 的 `chunks/node.js` 相关行。结果：确认 R-01，不执行网络调用或服务启动。
5. 触发：开发方修正 R-01，需要复核受影响差异。操作：只读重读 `frontend/.env.example`、README 第 142—176 行、HANDOFF 第 55—67 行、刷新差异中的代理说明、开发验证报告反馈章节，并用 `Get-FileHash` 对照既有 Vite 配置基线。结果：错误配置已删除，终端配置和恢复步骤与实际 `process.env` 读取方式对应，配置原字节未变，R-01 关闭。

## 限制与下一步

本次是交接范围的独立代码/文档审查；没有验证完整空库容器启动、全业务回归、付费模型、真实账号发布、数据库写入、生产部署或 Git 发布，也没有认定所有历史文档、截图和客户信息已脱敏。R-01 已完成聚焦复核；Tester 仍需独立完成聚焦验证并拥有最终任务验证结论。
