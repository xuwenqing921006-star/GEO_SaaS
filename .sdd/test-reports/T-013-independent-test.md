# T-013 / T-014 独立 Tester 技术验收报告

- 验收时间：2026-07-28 07:04（Asia/Shanghai）
- Tester：独立 Tester（非 Developer）
- 验收对象：T-013 全系统安全、性能、备份与可部署包；T-014 独立 Tester 技术验收阶段
- 最终结论：**PASS**
- 技术阻断：**无**
- 生产部署：**未执行**

## 1. 接受标准结论

| 接受标准 | 独立结果 | 证据摘要 |
| --- | --- | --- |
| Reviewer 最终审查 | PASS | `.sdd/evidence/T-013-code-review.md` 最终结论 PASS；P0/P1/P2 均为 0 |
| 66 个 OpenAPI 接口与契约一致 | PASS | 契约测试通过；独立统计 66/66；三个嵌套数组请求 DTO 的标题、属性与 required 集合逐项一致 |
| 前后端格式、Lint、类型、单元、集成、契约、构建 | PASS | `pnpm check` 全绿；后端 150 passed、5 个环境门控测试随后在真实 PostgreSQL 中 5/5 通过；前端 40/40 |
| 可关闭 Mock 的真实全旅程 E2E | PASS | `VITE_USE_MOCK=false`，Chromium 11/11；使用独立临时后端、SQLite 与端口 |
| AI 优先文章生产与文章列表 | PASS | 浏览器覆盖“AI 生成新文章 → 生成中 → 文章列表 → 生成稿 → 人工生成后编辑 v2 → GEO 优化 v3 → 导出”；没有空白人工草稿入口 |
| 跨行业通用性 | PASS | 真实浏览器覆盖家政建档、维修资料修复；后端金标覆盖少儿美术、家政、维修并验证家政/维修无少儿美术硬编码 |
| 安全与 Secret 卫生 | PASS | Bandit、pnpm audit、pip-audit、Secret 形态扫描全部通过；未读取或输出真实 API Key |
| 严重/高危镜像漏洞为 0 | PASS | 六个最终镜像逐一 Docker Scout 扫描，均为 0 Critical / 0 High |
| 目标容量与 PostgreSQL 并发锁 | PASS | 正式角色授权模型的随机临时库中 5/5；包含 100,000 监测样本容量目标 |
| 备份、恢复和数据库事务回滚 | PASS | 随机隔离生产栈完成加密备份、周备份恢复、哈希/计数校验、篡改恢复失败与恢复失败后的数据库回滚 |
| HTTPS/HSTS、Worker 与内部指标 | PASS | Windows PowerShell 5 最终演练通过 `https_hsts`、Worker readiness 与 internal metrics |
| Chromium / Microsoft Edge 生产烟测 | PASS | 当前镜像 2/2；回切上一兼容镜像后 Chromium 1/1；重新前滚当前镜像后 Chromium/Edge 2/2 |
| 上一镜像回滚 | PASS | `0.1.0-rc13 → 0.1.0-pre-rc13 → 0.1.0-rc13`，同一临时数据库保持可用 |
| ECC V2 状态一致性 | PASS | `ECC_V2.cmd doctor`：`PASS: ECC V2 doctor found no inconsistencies` |
| 当前开发服务健康 | PASS | `127.0.0.1:8000` 为 ready，数据库/存储/Worker 均 ok；`127.0.0.1:5173/login` 为 200 |

## 2. OpenAPI 独立核验

执行：

```text
uv run pytest tests/test_openapi_contract.py -q -vv
```

结果：`1 passed`。

另由 Tester 直接从应用生成 OpenAPI 并独立统计：

- GET/POST/PUT/PATCH/DELETE 操作总数：66。
- 创建问题集的 `questions[]`：`QuestionInput`，属性为
  `id/text/family/is_brand_query/target_level/priority`，必填为
  `text/family`。
- 修改问题集的 nullable `questions[]`：正确解包 `anyOf` 后仍为相同
  `QuestionInput`。
- 人工样本的 `items[]`：`ManualSampleInput`，属性为
  `sample_id/status/raw_answer/failure_reason/asked_at`，必填为
  `sample_id/status/asked_at`。

三个嵌套请求检查均通过。

## 3. 完整质量门禁与覆盖率

### 3.1 全量门禁

```text
pnpm check
```

结果：

- Prettier：PASS。
- Ruff format：85 files PASS。
- ESLint：PASS。
- Ruff check：PASS。
- Vue/TypeScript typecheck：PASS。
- Mypy：27 source files PASS。
- Workspace 结构测试：4/4。
- 前端单元测试：40/40。
- 后端测试：150 passed、5 skipped。
- 前端生产构建：PASS。
- Python compile：PASS。
- Compose 生产示例配置解析：PASS。

上述 5 个 skip 仅由 `TEST_POSTGRES_DATABASE_URL` 环境门控。Tester 随后按
`backend/postgres/bootstrap-roles.sh` 的正式角色授权模型创建随机临时数据库，
执行空库迁移至 `0013` 后重跑：

```text
uv run pytest tests/jobs/test_postgres_job_locking.py \
  tests/monitoring/test_monitoring_postgres.py \
  tests/performance/test_monitoring_capacity.py -q -vv
```

结果：`5 passed`，包含：

- Worker `SKIP LOCKED` 防重复领取。
- 客户事实集锁串行化。
- 内容版本并发写入只允许一次成功。
- 监测问题集与批次创建锁串行化。
- 100,000 监测样本指标容量目标。

临时数据库和两个临时角色在测试后删除，未修改 `geo_saas_t008` 数据。

### 3.2 覆盖率

```text
pnpm test:coverage
```

结果：

- 后端全体语句覆盖率：84.61%，门槛 75%。
- 固定核心分支覆盖率：88.27%，门槛 85%。
- 覆盖率命令独立重跑了后端测试，门槛检查通过。

## 4. 真实 API 浏览器全旅程

```text
pnpm --dir frontend test:e2e -- \
  --project=chromium \
  --output=e2e/.playwright-results-t013-independent
```

结果：`11 passed`，2.2 分钟。测试配置明确使用
`VITE_USE_MOCK=false`，启动独立后端端口 8003、前端端口 5174 和临时
SQLite，不依赖当前开发数据。

覆盖：

- 登录、搜索、创建客户、退出与会话恢复。
- 1024/1280 桌面布局与横向溢出检查、小视口桌面限定提示。
- 家政客户真实建档。
- 维修客户真实资料上传与修复。
- 诊断和关键词/内容计划。
- 设置页缺少真实模型配置时 fail closed。
- AI 生成文章、生成状态、文章列表、生成稿、生成后编辑、GEO 优化、版本不可变与导出。
- 渠道推荐及人工分发边界。
- 多平台 AI 可见性监测。

本轮特别确认：

- 人工不负责从空白正文写文章。
- 系统先根据企业事实、关键词、目标问题、GEO 建议和事实边界生成文章。
- 人工只在生成后编辑。
- 文章以列表展示并保留版本。
- 产品不自动发布、不回填链接/截图、不承诺一定被收录或推荐。

## 5. 安全与供应链

执行与结果：

```text
uv run bandit -r app -q
# exit 0

pnpm audit --prod --audit-level high
# No known vulnerabilities found

uvx pip-audit@2.10.0 --path backend/.venv/Lib/site-packages --skip-editable
# No known vulnerabilities found

uv run pytest tests/test_secret_hygiene.py -q -vv
# 1 passed
```

说明：

- Secret 检查只扫描业务源码、配置示例和交付材料的危险密钥形态。
- Tester 没有读取、回显或写入真实 DeepSeek、千问或其他模型 API Key。
- E2E、容量与生产演练均使用一次性测试凭据；报告不记录凭据。
- 完整后端测试同时覆盖 Session、CSRF、限流、跨客户隔离、上传校验、
  日志脱敏、幂等、乐观锁、模型失败降级和未授权资料阻断。

## 6. 最终镜像、摘要与漏洞扫描

```text
docker compose --env-file .env.production.example \
  -f compose.yaml -f compose.production.yaml \
  build api worker web caddy backup
```

构建成功。最终本地镜像摘要如下：

| 镜像 | SHA-256 digest | Scout Critical | Scout High |
| --- | --- | ---: | ---: |
| api | `8ef4c9a0c311d6ea826d71d8b697c5c7934ed192cbaa4c3bca58d06adc14d1e8` | 0 | 0 |
| worker | `c8c9d22dcb2392187a72601e1c2bd18e5641ef6cca021da701b9260bca5e11ab` | 0 | 0 |
| web | `0ae7b428e00874be692b5ef9383602924929d63c1212e18a80fa9ade1a18d961` | 0 | 0 |
| caddy | `5b1128de8b7b4ea116b125fe8587f9642a8051beb320fc8f6ca5395c71834228` | 0 | 0 |
| backup | `813257bdcf8848666dd8b436c6441d348c556a053a9fbfccc8d453113632e4ea` | 0 | 0 |
| postgres | `6778820d3a91853ece431e9af9e3005b9cb029c8d0c93295fd6c559003273a85` | 0 | 0 |

每个镜像均以如下方式逐一独立扫描：

```text
docker scout cves --only-severity critical,high --exit-code \
  local://geo-saas/<image>:0.1.0-rc13
```

六次均 exit 0，均为 `0C 0H`。

## 7. 随机隔离生产演练

最终 Windows-first 命令：

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File scripts/t013_release_drill.ps1
```

最终结果：exit 0，随机项目
`geo-saas-t013-a35532fad493` 完整通过：

```text
production_drill=passed
weekly_backup_after_daily_removal=passed
transactional_restore=passed
post_validation_database_rollback=passed
internal_metrics=passed
https_hsts=passed
```

演练实际验证：

1. 启动带 PostgreSQL、API、Worker、Web、Caddy、Backup 的生产 Compose 栈。
2. HTTPS ready 返回成功，Worker heartbeat 为 ok。
3. 读取内部指标成功，数据库与 Worker 不暴露公网端口。
4. 强制生成加密日备份，并复制为周备份。
5. 删除日备份后，仅用周备份解密、校验并恢复。
6. 校验数据库计数、文件哈希和 Worker heartbeat。
7. 写入数据库保护值，制作“加密与哈希有效、但恢复后计数校验故意不一致”的备份。
8. 恢复按预期失败，并自动回滚数据库；保护值仍为原值。
9. 恢复后再次验证 readiness 与 HSTS。
10. 清理随机项目的容器、卷、网络、备份和临时 age 私钥。

另以 PowerShell 7.6.4 执行同一演练也通过。

### 7.1 验收中发现并关闭的问题

Tester 首次使用 Windows PowerShell 5 发现三处 Windows-first 兼容问题：

- 老版本 .NET 不支持 `RandomNumberGenerator.Fill`。
- 原生命令把正常信息写入 stderr 时，在
  `$ErrorActionPreference = "Stop"` 下会产生 `NativeCommandError`。
- Windows PowerShell 5 的 `Invoke-WebRequest` 不支持
  `-SkipCertificateCheck`，且 curl header 数组必须保留换行后才能匹配 HSTS。

Developer/主代理完成兼容修复后，Tester 每次都从相同
`powershell.exe` 命令重新独立执行。最终完整演练 exit 0，且失败路径不会掩盖
原异常，PASS 标记只在清理成功后输出。

## 8. 生产 HTTPS 浏览器烟测与镜像回滚

Tester 另建独立生产栈并创建一次性负责人，不使用现有开发数据。

当前镜像：

```text
pnpm --dir frontend test:e2e:t013
```

结果：Chromium 1/1、Microsoft Edge 1/1。

随后在同一数据库与 HTTPS 入口回切：

```text
APP_VERSION=0.1.0-pre-rc13
docker compose ... up -d --no-build --no-deps api worker web
```

结果：ready；Chromium 1/1。

重新前滚至 `0.1.0-rc13` 后：

- ready；
- Chromium 1/1；
- Microsoft Edge 1/1。

生产烟测同时断言：

- HTTPS 可访问。
- 数据库、存储、Worker 均 ready。
- HSTS `max-age=31536000`。
- CSP、`X-Content-Type-Options`、`X-Frame-Options` 与
  `Referrer-Policy` 生效。
- 登录后进入客户工作台。

独立栈、数据库卷和网络已全部清理。

## 9. T-014 技术验收边界

独立 Tester 阶段结论：**PASS**。

业务边界与实现一致：

- 仅 Web。
- 单负责人；客户不登录。
- 本地服务行业通用，不把师资、课程等字段强加给所有行业。
- 无审核流。
- 无自动发布。
- 无链接或截图回填要求。
- 无“保证收录、排名或推荐”的效果承诺。
- 文章由 AI 先生成，人工仅在生成后修改。

T-014 仍包含 Product Manager 业务接受和产品负责人最终 Web/user gate；这两项
属于后续职责分离门禁，不是本次 Tester 技术阻断。生产云资源、域名、付费服务
和生产部署仍需产品负责人另行明确授权。

## 10. 清理与最终状态

- 所有随机临时 PostgreSQL 数据库与角色：已删除。
- 所有 T-013 临时 Compose 容器、卷与网络：0 残留。
- 临时加密备份和 age 私钥：已删除。
- 当前 `geo_saas_t008` 数据：未修改。
- 当前开发 API：ready；数据库、存储、Worker 均 ok。
- 当前开发 Web 登录页：HTTP 200。

**最终判定：T-013 PASS；T-014 独立 Tester 技术阶段 PASS；技术阻断 0。**
