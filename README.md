# GEO SaaS

面向本地服务企业的 Web 工具，由一个运营负责人管理客户、企业知识库、GEO 诊断、关键词、内容生成、发布账号和 AI 可见性监测。工程由 Web、API、Worker 和 PostgreSQL 组成。

本项目可独立安装、运行和继续开发。无需 ECC_V2，团队可自行选择 IDE、AI 工具和协作流程。当前为开发交接基线，仍有未完成和待验收事项，不能据此认定已完成生产发布。

- [开发交接说明](docs/handoff/HANDOFF.md)：模块、资料、配置、数据与账号交接。
- [未完成任务清单](docs/handoff/OPEN-TASKS.md)：38 项进行中、1 项失败的历史业务任务及逐项验收要求。
- [项目约定](AGENTS.md)：工具无关的开发约定。
- [GitHub 仓库与协作](docs/handoff/REPOSITORY.md)：仓库地址、克隆与分支协作。
- [数据库表结构＋演示数据](database/README.md)：可以直接导入 PostgreSQL 18 的 SQL 包，不要求 Docker；包含 41 张业务表和全新虚构数据。

## 环境与目录

| 工具 | 项目要求 |
| --- | --- |
| Node.js | 24.x；`package.json` 限定 `>=24 <25` |
| pnpm | 10.33.0；以 `packageManager` 和锁文件为准 |
| Python | 3.13.x；`backend/pyproject.toml` 限定 `<3.14` |
| uv | 本次本机检查版本 0.11.30；按 `backend/uv.lock` 安装 |
| PostgreSQL | 18；默认由项目 Dockerfile 构建 |
| Docker | Docker Engine/Desktop + Compose v2；Windows 使用 Linux containers |
| Chrome / Edge | 真实浏览器发布需要；推荐在 Windows 原生运行 API/Worker |

`frontend/` 是 Vue 3 + TypeScript 客户端，`backend/app/` 是 FastAPI 与 Worker，`backend/migrations/` 是 Alembic 迁移，`backend/tests/` 和 `frontend/tests/` 是自动化测试，`frontend/e2e/` 是浏览器测试，`ops/` 是部署与备份脚本，`docs/` 是需求、接口、架构与交接资料。

下面的主流程命令使用 PowerShell，工作目录为项目根目录。首次安装需要访问依赖仓库和容器镜像仓库；不要混用 npm、yarn 与 pnpm 更新锁文件。

## 路径一：容器运行核心服务

适合从零启动 Web、API、Worker 和数据库。先确认 5173 端口可用；本机若已运行原生前端，可在自己的 `.env` 将 `WEB_PORT` 改为其他端口，例如 5180。

1. 复制开发配置，仅在目标文件不存在时执行：

```powershell
Copy-Item .env.example .env
```

2. 为新的独立环境生成主密钥并写入 `.env`。它用于加密保存模型凭据；已有环境应保留原密钥，不要重新生成：

```powershell
$devKeyBytes = New-Object byte[] 32
$devKeyGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
$devKeyGenerator.GetBytes($devKeyBytes)
$devKeyGenerator.Dispose()
$devMasterKey = [Convert]::ToBase64String($devKeyBytes).Replace('+', '-').Replace('/', '_')
$devEnvironmentLines = Get-Content -LiteralPath .env
$devEnvironmentLines -replace '^GEO_APP_MASTER_KEY=.*$', ('GEO_APP_MASTER_KEY=' + $devMasterKey) |
    Set-Content -LiteralPath .env -Encoding utf8
Remove-Variable devMasterKey,devKeyBytes,devEnvironmentLines
```

`.env.example` 中的密码仅用于本机开发。正式环境使用独立强密码和安全配置渠道；真实环境文件不进入 Git。

3. 检查配置并启动。固定项目名称让数据库卷、文件卷和服务名称稳定：

```powershell
docker compose -p geo-saas-dev --env-file .env config --quiet
docker compose -p geo-saas-dev --env-file .env up -d --build --wait
docker compose -p geo-saas-dev --env-file .env ps
```

API 首次启动自动执行 `alembic upgrade head`；数据库入口脚本建立独立运行角色和迁移角色。首次构建可能较慢。默认 Web 为 [http://127.0.0.1:5173](http://127.0.0.1:5173)，通过 Web 的 `/api` 代理访问后端；基础 Compose 不向主机映射 8000 或数据库端口。

4. 新空库需要初始化唯一负责人。用户名至少 3 字符，密码至少 12 字符；没有自动创建的通用默认登录密码：

```powershell
$ownerInitialSecret = Read-Host '负责人初始密码（至少12位）' -AsSecureString
$env:OWNER_BOOTSTRAP_PASSWORD = [System.Net.NetworkCredential]::new('', $ownerInitialSecret).Password
try {
    docker compose -p geo-saas-dev --env-file .env exec `
        -e OWNER_BOOTSTRAP_USERNAME=owner `
        -e OWNER_BOOTSTRAP_DISPLAY_NAME=平台负责人 `
        -e "OWNER_BOOTSTRAP_PASSWORD=$env:OWNER_BOOTSTRAP_PASSWORD" `
        api python -m app.bootstrap_owner
} finally {
    Remove-Item Env:OWNER_BOOTSTRAP_PASSWORD
    Remove-Variable ownerInitialSecret
}
```

该命令拒绝覆盖已有负责人。使用自己设置的密码登录，在设置页配置模型。不要复制测试账号密码作为正式负责人密码。

5. 检查真实服务状态：

```powershell
Invoke-RestMethod http://127.0.0.1:5173/api/v1/health/live
Invoke-RestMethod http://127.0.0.1:5173/api/v1/health/ready
```

`live` 应返回 `ok`，`ready` 应返回 `ready` 且 database、storage、worker_heartbeat 均为 `ok`。若 `WEB_PORT` 已更改，URL 同步更改。

```powershell
docker compose -p geo-saas-dev --env-file .env logs --tail 50 api worker db
docker compose -p geo-saas-dev --env-file .env stop
docker compose -p geo-saas-dev --env-file .env start
```

`stop/start` 保留数据。删除卷会丢失数据库或上传文件，不作为普通重启步骤。

容器镜像没有配置桌面浏览器和可见登录环境。真实自媒体登录、人工安全验证与浏览器发文请按下一条原生开发路径核验；核心服务启动成功不代表已通过真实渠道发布验收。

## 路径二：Windows 原生开发与浏览器账号操作

API、Worker 和前端运行在主机，数据库由 Compose 提供。此路径与上面的完整容器运行择一使用，避免同时运行两套服务处理同一数据库。

在项目根目录安装锁定依赖：

```powershell
pnpm install --frozen-lockfile
uv sync --project backend --frozen
```

准备根目录 `.env` 后，启动数据库服务。开发覆盖层仅将数据库绑定到本机 55432 端口；该端口被占用时，在根 `.env` 设置 `DEV_DB_PORT`，并同步设置后端 `.env` 的 `DB_PORT`：

```powershell
docker compose -p geo-saas-dev --env-file .env -f compose.yaml -f compose.dev.yaml config --quiet
docker compose -p geo-saas-dev --env-file .env -f compose.yaml -f compose.dev.yaml up -d --build --wait db
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
```

复制命令仅用于新环境，不覆盖已有配置。后端使用 `backend/.env`，前端使用 `frontend/.env.local`。后端的数据库名、运行角色、迁移角色和密码必须与根 `.env` 中的 Compose 配置一致。

在 `backend/.env` 的 `APP_MASTER_KEY` 填入该环境的主密钥；它与 Compose 的 `GEO_APP_MASTER_KEY` 表示同一项设置，名称不同。API 与 Worker 必须使用同一主密钥和 `STORAGE_ROOT`。新环境可在后端目录按上面的生成方法，把替换模式改为 `^APP_MASTER_KEY=.*$`、替换值改为 `APP_MASTER_KEY=`；已有数据保留对应的原密钥。

终端 A，工作目录 `backend/`，先迁移，再初始化账号和启动 API：

```powershell
Set-Location backend
uv run alembic upgrade head
```

初始化时沿用上面的隐藏输入和 `try/finally`，将容器命令替换为 `uv run python -m app.bootstrap_owner`，并先设置 `$env:OWNER_BOOTSTRAP_USERNAME='owner'` 和 `$env:OWNER_BOOTSTRAP_DISPLAY_NAME='平台负责人'`。只在新空库执行一次。随后：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

终端 B，工作目录 `backend/`：

```powershell
uv run python -m app.worker
```

终端 C，工作目录为项目根目录：

```powershell
pnpm --dir frontend dev
```

访问 [http://127.0.0.1:5173](http://127.0.0.1:5173)。原生 API 健康检查为 `http://127.0.0.1:8000/api/v1/health/ready`；`ready` 需要 Worker 运行。Vite 的 `/api` 默认代理到本机 8000。真实发布需安装 Chrome/Edge；可在后端配置 `BROWSER_EXECUTABLE_PATH` 指向自己电脑上的程序。

如果将 API 改为其他端口，启动前端前在该终端设置代理目标，例如 API 为 8002：

```powershell
$env:VITE_API_PROXY_TARGET='http://127.0.0.1:8002'
pnpm --dir frontend dev
```

当前 Vite 配置从进程环境读取代理目标；仅在 `.env.local` 填写 `VITE_API_PROXY_TARGET` 不会更改代理。改回默认时，在同一终端执行 `Remove-Item Env:VITE_API_PROXY_TARGET` 并重启 Vite。

`backend/scripts/start-local-api.ps1` 和 `start-local-worker.ps1` 是原作者的历史本机辅助脚本，写死旧数据库容器、库名和管理员身份；本次保留文件，不作为新环境启动入口。

## 前端 Mock 预览

只需要预览界面时，可不启动数据库或 API：

```powershell
$env:VITE_USE_MOCK='true'
pnpm --dir frontend dev
```

开发 Mock 使用任意非空用户名和密码；这不是负责人真实账号。恢复真实 API 前，在同一终端执行 `Remove-Item Env:VITE_USE_MOCK` 并重启 Vite，确认 `.env.local` 中为 `false`。生产构建强制排除 Mock。

## 验证命令

以下命令在项目根目录运行，依赖已安装。它们不要求外部开发框架：

| 范围 | 命令 |
| --- | --- |
| 工程文件结构 | `pnpm test:structure` |
| 格式 | `pnpm format:check` |
| Lint | `pnpm lint` |
| 类型 | `pnpm typecheck` |
| 单元和常规后端测试 | `pnpm test:unit` |
| 构建 | `pnpm build` |
| Compose 基础配置 | `pnpm compose:check` |
| 汇总检查（不含 E2E 和覆盖率） | `pnpm check` |
| 后端定向检查 | `uv run --project backend pytest -c backend/pyproject.toml backend/tests/publishing -q` |
| 覆盖率 | `pnpm test:coverage` |

浏览器测试先安装测试浏览器，再运行：

```powershell
pnpm --dir frontend exec playwright install chromium
pnpm --dir frontend test:e2e
```

主 E2E 配置使用临时 SQLite、固定模型与发布模拟，自动启动 8003/5174 端口的隔离测试服务，不复用本机业务服务；部分专用配置使用其他端口，详见 `frontend/e2e/`。配置中带 `real` 的文件名代表使用 API 接口，不表示向真实平台发文。

PostgreSQL 锁、并发和容量专项需要单独准备隔离测试库并显式提供 `TEST_POSTGRES_DATABASE_URL`；普通测试可能跳过它们，跳过不代表通过。当前覆盖率脚本要求全后端语句 75%、指定核心模块分支 85%，与旧报告中的阈值可能不同，按实际脚本和团队后续约定执行。

本轮交接整理只验证文档、环境示例、Compose 解析和工程结构；没有重新执行全量业务测试。历史测试结果、失败与后续修复的区别见未完成任务清单。

## 配置、数据与协作

- `.env`、`backend/.env`、`frontend/.env.local`、密钥、备份、上传资料、浏览器会话和生成日志不提交到 Git。
- 源码可从 Git 重建环境，现有客户资料不会随源码自动迁移；数据迁移和凭据交接见 [交接说明](docs/handoff/HANDOFF.md)。
- 后续开发建议每项变更使用独立分支和 PR，说明验证结果；团队可自行选择审查与任务管理方式。
- 2026-10-13 的交接整理阶段只初始化本地仓库；后续源码提交与仓库协作见 GitHub 说明。源码上传不表示已完成业务验收或生产部署。
- 生产部署、加密备份与回滚见 [运维手册](docs/delivery/Operations-Runbook.md)；[历史发布检查清单](docs/delivery/Release-Checklist.md) 与旧报告不等于当前版本已验收。
- 第三方依赖归属见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
