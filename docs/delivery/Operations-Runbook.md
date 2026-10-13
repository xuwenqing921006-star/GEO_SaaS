# GEO SaaS 单机部署、备份与回滚手册

适用范围：V1 Web 的单台 Linux 主机交付包。本文只说明可部署与演练流程，不代表已经生产上线。购买云主机、域名、主机外存储以及执行生产部署，必须另行获得产品负责人明确授权。

## 1. 生产拓扑

- Caddy 是唯一公网入口，只暴露 80、443 和 443/UDP。
- Web、API 只在 Compose 网络通信；Web 的 5173 映射仅绑定主机 `127.0.0.1`，不对公网开放。
- PostgreSQL 和 Worker 只加入内部 `backend` 网络，没有主机端口。
- 数据库卷、业务文件卷、Caddy 状态卷和备份卷相互隔离。
- API、Web、Worker、数据库和备份服务都启用最小权限、只读根文件系统或禁止提权等约束。

## 2. 首次准备

1. 从 `.env.production.example` 复制主机专用环境文件，保存到项目目录之外。
2. 分别生成管理员、运行时和迁移账号的高强度独立密码。
3. 生成 32 字节、带正确 Base64 填充的 URL-safe 主密钥，填入 `GEO_APP_MASTER_KEY`。Linux 可用 `openssl rand -base64 32 | tr '+/' '-_'`；PowerShell 可用 `[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('+','-').Replace('/','_')`。不要删除末尾的 `=`。
4. 在离线安全位置生成 age 密钥对。环境文件只保存 `age1...` 公钥；私钥文件权限设为仅主机管理员可读。
5. 配置 `APP_DOMAIN`，将域名 DNS 指向主机。Caddy 会自动申请和续期 TLS 证书。
6. 由主机备份代理只读取 `backup_data` 中的 `.tar.age` 与 `.sha256` 密文文件，并复制到主机外存储；应用容器不保存云存储凭据。

生产配置预检：

```bash
docker compose \
  --env-file /secure/geo-saas.production.env \
  -f compose.yaml \
  -f compose.production.yaml \
  config --quiet
```

## 3. 启动与发布

发布前必须记录当前镜像 digest、当前 Alembic 版本、数据库备份文件和文件卷快照。

```bash
docker compose \
  --env-file /secure/geo-saas.production.env \
  -f compose.yaml \
  -f compose.production.yaml \
  build

docker compose \
  --env-file /secure/geo-saas.production.env \
  -f compose.yaml \
  -f compose.production.yaml \
  up -d
```

首次启动并完成迁移后，通过容器内的一次性环境变量创建唯一负责人。密码不会写入镜像、Compose 文件或日志，命令也不会覆盖已存在的负责人：

```bash
read -rsp "负责人初始密码: " OWNER_PASSWORD
docker compose \
  --env-file /secure/geo-saas.production.env \
  -f compose.yaml \
  -f compose.production.yaml \
  exec \
  -e OWNER_BOOTSTRAP_USERNAME=owner \
  -e OWNER_BOOTSTRAP_DISPLAY_NAME=平台负责人 \
  -e OWNER_BOOTSTRAP_PASSWORD="$OWNER_PASSWORD" \
  api python -m app.bootstrap_owner
unset OWNER_PASSWORD
```

启动后检查：

- `https://域名/api/v1/health/live` 返回 200。
- `https://域名/api/v1/health/ready` 的数据库、文件存储和 Worker 均为 `ok`。
- 响应包含 HSTS、CSP、`X-Content-Type-Options`、`X-Frame-Options`、Referrer Policy 和 Permissions Policy。
- 登录 Cookie 在生产环境包含 `Secure`、`HttpOnly`（Session）和 `SameSite=Lax`。
- 主机公网监听中不存在 PostgreSQL 或 Worker 端口。

## 4. 自动备份

`backup` 服务每天北京时间 10:15（容器 UTC 02:15）执行：

1. 用迁移账号生成 PostgreSQL custom-format dump。
2. 生成业务文件卷 tar。
3. 保存客户、事实、内容版本、监测样本计数及 Alembic 版本。
4. 生成内部文件哈希和归档哈希。
5. 在 tmpfs 中组装明文后，通过 age 公钥加密到备份卷。
6. 每日备份保留 14 天；周日副本保留 56 天。
7. 主机备份代理按企业现有备份策略将只有密文的备份复制到主机外。

立即执行一次备份：

```bash
docker compose \
  --env-file /secure/geo-saas.production.env \
  -f compose.yaml \
  -f compose.production.yaml \
  exec backup /usr/local/bin/geo-backup
```

每次发布前必须确认最新 `.tar.age` 和外层 `.sha256` 均存在，且主机外副本已完成。

## 5. 隔离恢复演练

恢复会清理目标测试数据库和目标文件卷，只能在隔离环境执行。先停止隔离环境的 API 和 Worker，再运行 restore profile；`CONFIRM_RESTORE` 必须精确匹配目标数据库名。

```bash
docker compose \
  --env-file /secure/geo-saas.restore-test.env \
  -f compose.yaml \
  -f compose.production.yaml \
  --profile restore \
  run --rm \
  -e BACKUP_FILE=/backups/daily/geo-saas-YYYYMMDDTHHMMSSZ.tar.age \
  -e CONFIRM_RESTORE=restore-geo_saas_restore_test \
  -v /secure/geo-saas-backup.agekey:/run/secrets/backup_age_identity:ro \
  restore
```

恢复程序会依次验证密文哈希、解密、验证内部归档、保存目标数据库和文件卷快照、恢复数据库、比较四类业务计数、恢复文件并逐文件校验哈希。任一步失败都会以非零状态退出；如果数据库已经替换，程序会先自动恢复演练前的数据库快照。一次性恢复容器只增加文件覆盖和属主修复所需的两项系统能力，不继承压缩包中的属主信息，并在完成或回滚后把业务文件归还给普通应用身份。

恢复演练通过标准：

- 客户、事实、内容版本、监测样本计数与备份一致。
- 文件数量和全部 SHA-256 一致。
- Alembic 版本与备份一致。
- API / Worker 启动后 ready，负责人可登录并读取客户、内容和监测结果。
- 测试恢复耗时不超过 60 分钟；生产目标 RPO 24 小时、RTO 8 小时。

## 6. 应用与数据库回滚

1. 立即停止 Worker，阻止新模型调用、解析、导出和监测写入。
2. 保留现场日志，记录错误时间、版本、请求 ID 和影响客户。
3. 如果新旧应用兼容当前 Schema，把安全环境文件中的 `APP_VERSION` 改回发布前记录的版本标签，并确认该标签对应的镜像 digest 与发布记录一致；随后执行 `docker compose ... up -d --no-build web api worker`。
4. 只有对应 Alembic downgrade 已在备份副本验证通过时，才允许降级 Schema。
5. Schema 不兼容或数据已损坏时，不在原库尝试修补；从发布前加密备份恢复数据库和文件卷。
6. 恢复后重新执行计数、文件哈希、健康检查和关键 Web 冒烟。
7. 确认无跨客户、密钥、事实或版本完整性问题后再恢复 Worker。

必须立即停止 Worker 并回滚的情况：

- 跨客户读取或写入。
- 模型密钥、密码、Session 或客户敏感原文泄露。
- 已确认事实被静默修改。
- 内容版本、导出或监测结果发生不可追溯覆盖。
- 新版本无法创建内容或任务持续重复产生付费调用。

## 7. 监控与保留

- 关注就绪检查、5xx 比例、队列深度、最老任务等待时间、Provider 成功率、降级率、模型预算、磁盘和备份结果。
- 队列最老任务超过 20 分钟、日预算达到 80%、磁盘达到 80%、备份一次失败或就绪连续失败 5 分钟时告警。
- API 内网地址 `/internal/metrics` 输出 Prometheus 文本指标；生产入口不转发 `/internal`，仅允许同一 Docker 网络中的监控采集器读取。
- Worker 对首次出现的阈值告警写入结构化 `operational_alert` 日志，恢复时写入 `operational_alert_resolved`，避免每个心跳重复告警。
- 备份容器每次执行都会原子更新 `/backups/backup-status.json`；API 与 Worker 只读挂载该状态，失败和超过 26 小时未成功会进入告警。
- 指标包括请求总量/5xx/耗时、任务队列深度/最老等待时间、Provider 调用成功/降级/Token/费用/预算、业务文件用量/磁盘容量和备份结果。
- 容器日志使用 JSON 输出，由主机日志系统设置容量上限和保留周期。
- 每季度至少完成一次隔离恢复演练；每次发布至少验证一次发布前备份。
