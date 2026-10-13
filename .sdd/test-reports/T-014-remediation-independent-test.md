# T-014 补救版本独立技术验收报告

- 验收时间：2026-07-28 09:46（Asia/Shanghai）
- 验收角色：独立 Tester
- 验收对象：T-014 PA-01 / PA-02 最终补救版本
- 最终结论：**PASS**
- 阻断项：**无**
- 生产部署：**未执行**

本报告基于本轮重新执行的独立测试，不复用旧 Tester 结论，也不把
Developer 或 Reviewer 报告当作通过依据。Tester 未修改业务代码、产品验收
报告、任务状态、客户数据库数据或 Provider Key。

## 1. 验收矩阵

| 项目 | 结果 | 本轮独立证据 |
| --- | --- | --- |
| P06 建议写回 briefs | PASS | 后端专项 24/24；P06 真实 Chromium；写回后的每篇 brief 等于该篇前 4 个运营方可发布渠道 |
| brief 行锁与并发语义 | PASS | 在 55432 的随机隔离 PostgreSQL 库中直接持有 brief `FOR UPDATE`；渠道 Worker 确认等待，释放后完成写回 |
| P05 具名渠道成品 | PASS | 真实 Chromium 显示 3 张渠道成品卡；每张卡绑定独立版本、标题、正文预览、质量状态及 MD/DOCX 操作 |
| 非最后生成渠道编辑 | PASS | 选择知乎版本进入标题/正文编辑；保存后新增版本，知乎 mapping 更新到新版本 |
| 标题与正文质量门 | PASS | 无依据数字写入标题后文档 blocked、导出返回 422；坏正文同样不可导出 |
| 今日头条标题与重复生成 | PASS | 标题为真实问题式；无禁用短语；从渠道版再次生成不会叠加标题后缀 |
| P07 P0/P1 与分母 | PASS | 10 个 P0/P1 平台默认选中；夸克 P1 成功、微信 P1 失败；Web 显示有效 1、失败 1、分母 1/1 |
| API / 消费者端分开 | PASS | Web 可切换消费者端人工样本；失败样本保留在运行统计但不进入有效指标分母 |
| 全量门禁 | PASS | `pnpm check` 全绿；前端 40/40；后端 150 passed、5 个环境门控 skip |
| 完整真实浏览器回归 | PASS | `VITE_USE_MOCK=false`，Chromium 11/11 |
| 覆盖率 | PASS | statements 84.83%（4595/5417，门槛 75%）；core branches 88.27%（143/162，门槛 85%） |
| 最终镜像 | PASS | 六个 digest 与硬化证据完全一致；逐镜像 Scout 均 0 Critical / 0 High |
| PS5 生产演练 | PASS | 随机隔离栈六项全部 passed，容器、卷、网络均清理 |
| 当前开发服务 | PASS | 5173 登录页 HTTP 200；8000 ready，database/storage/worker 均 ok |
| ECC V2 一致性 | PASS | `ECC_V2.cmd doctor` 无不一致 |

## 2. P06 写回、行锁和并发语义

### 2.1 SQLite/API 与真实 Web

执行：

```text
uv run pytest tests/strategy/test_strategy_api.py \
  tests/channels/test_channels_api.py \
  tests/content/test_content_api.py \
  tests/monitoring/test_monitoring_api.py -q -vv
```

结果：`24 passed`。

其中 P06 专项实际断言：

- 新策略 brief 初始即包含适用渠道。
- 渠道推荐完成后，每篇 brief 的 `suggested_channel_ids` 等于该篇
  推荐结果中前 4 个 `operator_publishable` 渠道。
- 重复推荐形成新 generation；历史快照不被新目录内容追改。
- 不存在自动发布或第三方凭据接口。

执行：

```text
pnpm --dir frontend test:e2e:t011
```

该旅程也包含在最终 11/11 全量 Chromium 中并通过，证明 P06 从内容计划生成
运营方可执行的渠道建议。

### 2.2 PostgreSQL 行锁独立探针

Tester 使用现有 PostgreSQL 55432，但创建了随机、独立的新数据库及两个临时
角色；按正式 `bootstrap-roles` 权限模型授权并从空库迁移到 `0013`。未连接或
修改客户库数据。

探针步骤：

1. 创建独立客户、诊断、策略 bundle、content brief 和 running
   `channel_recommend` job。
2. 会话 A 对目标 `ContentBrief` 执行 `SELECT ... FOR UPDATE` 并保持事务。
3. 会话 B 启动真实 `process_channel_job`。
4. 等待 350ms，确认 Worker 尚未完成，证明没有绕过 brief 行锁。
5. 会话 A 把 brief 改为并发编辑版本 2 并提交。
6. Worker 获锁后重新读取并写回推荐。
7. 核对最终 4 个运营渠道、7 条总建议、job succeeded、brief version 3。

实际输出：

```text
brief_row_lock_wait=passed
concurrent_writeback_after_lock=passed
suggested_channels=4
brief_version=3
recommendations=7
```

随机数据库和临时角色测试后已删除；残留临时数据库为 0。

## 3. P05 渠道成品、编辑和导出

### 3.1 真实 Chromium

```text
pnpm --dir frontend test:e2e:t010
```

结果：`1 passed`，使用独立后端 8001、前端 5179，
`VITE_USE_MOCK=false`。

浏览器实际完成：

- AI 先生成主稿，人工只在生成后编辑。
- 手工编辑生成 v2，GEO 再优化生成 v3。
- 一次生成知乎、搜狐号、头条号 3 个具名渠道版本。
- 页面出现 3 张 `.channel-variant-card`。
- 头条卡片展示真实问题标题。
- 知乎和头条分别从各自卡片下载 Markdown，文件内标题与渠道 ID 不同。
- 选择非最后生成的知乎成品进入“编辑知乎成品”。
- 同时修改标题和正文后保存。
- 版本数从 6 增至 7，知乎卡片标题变为新标题，证明 mapping 指向新版本。
- 再输入坏正文后，质量面板变为“不可导出”，导出按钮禁用。

### 3.2 每张卡的精确版本和全部 MD/DOCX

Tester 独立检查当前 Web 绑定：

- 卡片以 `variant.id` 为 key，以 `variant.channel_id` 标识渠道。
- 标题、版本号和预览正文均取同一个 `variant.version`。
- 质量状态取该版本对应的 `variant.check`。
- Markdown 与 DOCX 两个按钮均把该卡的
  `variant.version.id` 作为 `source_version_id`。
- 质量 blocked 时两种导出都禁用。

为避免只验证按钮存在，Tester 又执行一次独立 API/文件探针：

- 生成知乎、搜狐号、头条号 3 个渠道版本。
- 核对 3 个不同 version ID、3 个不同正文、3 个非 blocked 质量检查。
- 对每个版本分别导出 Markdown 和 DOCX。
- 解码 Markdown，并用 `python-docx` 重新读取 DOCX。
- 六个文件都必须包含该版本精确标题和
  `本次适配渠道：<channel_id>`。

实际输出：

```text
named_channel_versions=3_distinct
named_channel_quality_gate=passed
named_channel_markdown_exports=3_passed
named_channel_docx_exports=3_passed
```

### 3.3 标题与正文质量门

后端专项本轮通过并明确覆盖：

- 向标题加入“成立于2010年并拥有100名教师”等无依据数字后，
  文档状态为 blocked。
- 对该 blocked 版本发起导出返回 422。
- 质量检查使用“标题 + 正文”整体，而不是只检查正文。
- 错误正文同样触发 `fact_consistency` 阻断。

### 3.4 今日头条标题

本轮后端与真实浏览器共同断言：

- 标题以 `即墨区少儿美术培训怎么选？` 真实问题开头。
- 不包含 `30 秒`。
- 标题与正文均不包含 `三十秒速读`。
- 不包含 `核验指南怎么`。
- 再次以已编辑渠道版请求生成头条版时，后端回退到最近非渠道主稿。
- 最终 `先看这些已确认信息` 只出现 1 次，没有叠加标题。

## 4. P07 P0/P1 监测闭环

```text
pnpm --dir frontend test:e2e:t012
```

结果：`1 passed`，使用独立后端 8002、前端 5181，
`VITE_USE_MOCK=false`；同一旅程也在全量 11/11 中再次通过。

浏览器实际断言：

- 国内主流 AI 目录展示 10 个平台。
- 10 个 P0/P1 平台默认全部选中。
- 创建首轮批次后展示 10 个平台组和超过 42 条样本。
- 页面明确显示“API 回答 ≠ 消费者端回答”。
- 切换“人工采样”后显示消费者端平台组。
- 夸克 P1 第一条人工样本提交成功，并出现 succeeded 状态。
- 微信 AI 搜索 P1 第一条记录为失败，保存明确失败原因，并出现 failed 状态。
- 切换“消费者端人工样本”后页面显示：
  - 失败 1 条；
  - 正确关联 100%；
  - 分母 `1 / 1`；
  - 上下文 `有效 1 · 失败 1 · 未执行 N`。

由此确认：失败样本保留在运行统计，但没有被计入有效 KPI 分母；API 与
消费者人工样本没有混算。

## 5. 全量门禁、真实浏览器和覆盖率

### 5.1 `pnpm check`

结果：exit 0，311.8 秒。

- Prettier：PASS。
- Ruff format：85 files PASS。
- ESLint：PASS。
- Ruff check：PASS。
- Vue/TypeScript typecheck：PASS。
- Mypy：27 source files PASS。
- Workspace 结构：4/4。
- 前端单元：40/40。
- 后端：150 passed、5 skipped。
- 生产前端 build：PASS。
- Python compile：PASS。
- Compose config：PASS。

5 个 skip 均是 `TEST_POSTGRES_DATABASE_URL` 环境门控。与本补救直接相关的
brief 行锁已由本轮随机 PostgreSQL 探针真实执行；此前五个正式 PostgreSQL
锁/容量测试不属于本次业务改动。

### 5.2 完整真实 Chromium

```text
pnpm --dir frontend test:e2e -- --project=chromium \
  --output=e2e/.playwright-results-t014-remediation-independent
```

结果：`11 passed`，3.0 分钟，`VITE_USE_MOCK=false`。覆盖：

- 登录、客户建档、Session 异常恢复与桌面布局。
- P02 真实资料上传与知识库。
- P03/P04 诊断和内容策略。
- P08 设置 fail closed。
- P05 AI 内容、渠道成品、编辑、质量与导出。
- P06 渠道建议。
- P07 多平台监测、人工成功/失败和指标分母。

### 5.3 覆盖率

为排除与全量测试并行执行的影响，Tester 又单独执行：

```text
pnpm test:coverage
```

结果：exit 0，332.3 秒。

- Whole-backend statements：4595 / 5417 = **84.83%**，门槛 75%。
- Core branches：143 / 162 = **88.27%**，门槛 85%。

Developer 曾记录 84.86%，但独立并行与独立单跑都稳定得到 84.83%。任务证据
已按较低、可复现值纠正为 84.83%；正式门槛未变化且通过，因此不构成阻断。

## 6. 镜像摘要与漏洞

当前本地最终镜像与
`.sdd/evidence/T-013-release-hardening.md` 逐字符一致：

| 镜像 | SHA-256 digest | Critical | High |
| --- | --- | ---: | ---: |
| API | `3794ec01cb0e50398faa401c0c0562e14c0fb99914370604d20f89bffe79605a` | 0 | 0 |
| Worker | `60033a07d20e4352fb107578a6d0ef71469ade5df5f954d6a535440b44cd3f8d` | 0 | 0 |
| Web | `17843c9824ca66908baf2c2847e9b467fb6153e9c0354d3cdb48ab4018c5c6ba` | 0 | 0 |
| Backup/Restore | `2f273587707614679a5e7bda40d5f56ad7cfc98450ef74f9c9f1fe1ed19296f0` | 0 | 0 |
| Caddy | `cc34d94a8f5d84c4649a60395c0f4d6192cf5a5ed200e60c7e058a2ec9b4ab3a` | 0 | 0 |
| PostgreSQL | `9def43566adf47cd1d4006e488b56300deb812ee494cf70e4356fafbdb5c1fd0` | 0 | 0 |

Tester 对六个镜像逐一执行：

```text
docker scout cves --only-severity critical,high --exit-code \
  local://geo-saas/<image>:0.1.0-rc13
```

六次均 exit 0，均为 `0C 0H`。

## 7. Windows PowerShell 5 生产演练

执行：

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File scripts/t013_release_drill.ps1
```

结果：exit 0，60.3 秒；随机项目
`geo-saas-t013-078338392a4f` 输出：

```text
production_drill=passed
weekly_backup_after_daily_removal=passed
transactional_restore=passed
post_validation_database_rollback=passed
internal_metrics=passed
https_hsts=passed
```

演练包含生产 Compose、API/Worker readiness、内部指标、加密备份、删除日备份后
用周备份恢复、文件哈希与数据库计数校验、篡改恢复失败、失败后的事务数据库
回滚以及 HTTPS/HSTS。

演练后独立检查：

- 该项目容器：0。
- 该项目命名卷：0。
- 该项目网络：0。

## 8. 当前服务、清理与边界

最终检查：

- `http://127.0.0.1:8000/api/v1/health/ready`：ready。
- database：ok。
- storage：ok。
- worker heartbeat：ok。
- `http://127.0.0.1:5173/login`：HTTP 200。
- 随机 T-014 临时数据库：0。
- 临时测试角色：0；仅保留部署本身已有的 `geo_migrator`。
- `ECC_V2.cmd doctor`：PASS，无不一致。

范围保持不变：

- 仅 Web、单负责人、客户不登录。
- 无自动发布。
- 无审核流。
- 无链接或截图回填要求。
- 不保证收录、排名或推荐效果。
- 未调用付费模型或外部生产系统。
- 未执行生产部署。

## 9. 最终判定

**PASS。**

T-014 PA-01 / PA-02 补救版本满足本轮全部独立技术验收要求；阻断项为 0。
Product Manager 的业务接受与产品负责人 user gate 仍由对应职责方完成，不由
Tester 代替。
