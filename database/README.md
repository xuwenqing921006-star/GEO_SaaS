# PostgreSQL 表结构与演示数据

这份交接包解决“拉到代码后还没有数据库和表”的问题。需要先有一个正在运行的 **PostgreSQL 18** 实例；它可以安装在 Windows、macOS、Linux 或 Docker 中。本包不要求 Docker，也不会把数据库服务器或真实经营数据打包进 Git。

## 包含内容

| 文件 | 内容 |
| --- | --- |
| [schema.sql](schema.sql) | 在全新隔离库执行全部 29 个迁移后导出的结构：41 张业务表、1 张 Alembic 版本表、索引、约束和外键；版本为 `0029` |
| [demo.sql](demo.sql) | 全新虚构的 2 家客户、12 条知识、12 条证据、12 个知识证据关联、2 份知识画像、2 份关键词策略和 6 个关键词 |
| [grants.sql](grants.sql) | 给运行角色 `geo_app` 授予数据读写权限，建表和后续迁移由数据库所有者负责 |
| [.env.example](.env.example) | 使用本机 PostgreSQL 的后端开发配置，模型与发布均默认固定模拟 |
| [manifest.json](manifest.json) | 版本、行数和 SQL 文件 SHA-256，供核对交接内容 |

没有负责人账号/密码、Session、API Key、渠道登录信息、真实客户、真实图片/文件、发布记录或待执行任务。企业名、地区、地址和证据都明确标记为虚构。

## 1. 准备 PostgreSQL

先安装并启动 PostgreSQL 18，确认终端里能使用 `psql`、`createuser` 和 `createdb`。如果系统找不到命令，把 PostgreSQL 的 `bin` 目录加入本机 PATH，再打开新终端。数据库运行在哪台机器、什么端口，与源码是否已经从 Git 拉取无关。

以下命令可在 macOS/Linux 终端或 PowerShell 执行，工作目录为项目根目录。示例假设本机 PostgreSQL 监听 `127.0.0.1:5432`。管理操作需要你自己实例的管理员角色；macOS 安装方式不同，管理员不一定叫 `postgres`，也可能是本机用户名。

如需指定管理员、地址和端口，在终端设置 `PGUSER`、`PGHOST`、`PGPORT`，不要把它们当作要提交的项目配置：

```bash
# macOS/Linux：将 <本机数据库管理员> 替换为自己的 PostgreSQL 管理员用户名
export PGUSER='<本机数据库管理员>'
export PGHOST=127.0.0.1
export PGPORT=5432
```

```powershell
# Windows PowerShell
$env:PGUSER='<本机数据库管理员>'
$env:PGHOST='127.0.0.1'
$env:PGPORT='5432'
```

## 2. 创建独立演示库并导入

只用于新建独立开发环境，不针对原有业务库执行。密码由你在命令提示中输入，不写在 SQL 文件里：

```bash
createuser --login --no-superuser --no-createdb --no-createrole --no-inherit --pwprompt geo_migrator
createuser --login --no-superuser --no-createdb --no-createrole --no-inherit --pwprompt geo_app
createdb --owner=geo_migrator geo_saas_demo
psql --username=geo_migrator --dbname=geo_saas_demo --set=ON_ERROR_STOP=1 --single-transaction --file=database/schema.sql --file=database/demo.sql --file=database/grants.sql
```

上面这组数据库工具命令也可直接在 PowerShell 执行。如果 `geo_migrator`、`geo_app` 已存在，保留其已有密码并跳过对应的 `createuser`；不要覆盖其他环境的账号。演示库已存在时先确认来源，不要为了重试删除原库或表。

`schema.sql` 拒绝导入已有公共表的数据库；整组导入使用单一事务，发生错误立即回滚。`demo.sql` 只允许空客户库或本演示库，重复导入同一演示数据不会覆盖既有记录。若不需要演示数据，从导入命令中去掉 `--file=database/demo.sql`。

本快照已经记录 `alembic_version=0029`，**不要再从 `0001` 重放迁移，也不要手工把版本改成其他值**。后续更新仍运行正常的 `alembic upgrade head`；当前版本会无改动通过。

## 3. 检查数据与权限

```bash
psql --username=geo_app --dbname=geo_saas_demo --set=ON_ERROR_STOP=1 --command="SELECT version_num FROM alembic_version; SELECT count(*) AS business_tables FROM information_schema.tables WHERE table_schema='public' AND table_name <> 'alembic_version'; SELECT standard_name, industry_name FROM clients ORDER BY standard_name; SELECT count(*) AS demo_facts FROM facts; SELECT count(*) AS demo_keywords FROM strategy_items;"
```

预期：版本 `0029`，业务表 41 张，客户 2 家，知识 12 条，关键词 6 个。负责人、模型凭据、发布账号和任务表保持为空。若出现 `permission denied`，用表所有者重新执行 `database/grants.sql`，不要把应用改成使用管理员身份。

## 4. 连接应用并创建自己的登录账号

首次创建配置时，从项目根目录执行：

```bash
# macOS/Linux，仅在目标文件不存在时复制
cp database/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

```powershell
# Windows PowerShell，仅在目标文件不存在时复制
Copy-Item database/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
```

把 `backend/.env` 的两个密码占位值替换为步骤 2 自己设置的密码，数据库名为 `geo_saas_demo`，端口与实际实例一致。这里没有使用 Docker，不需要创建根目录 `.env`。已有配置只修改所需字段，不覆盖旧主密钥或其他环境配置。

本演示默认固定模拟模式，可直接读取数据。以后需要保存加密的模型或渠道凭据时，按[项目 README](../README.md)为新环境生成 `APP_MASTER_KEY`，并让 API 与 Worker 使用同一密钥。

安装依赖：

```bash
pnpm install --frozen-lockfile
uv sync --project backend --frozen
```

负责人不随演示数据提供，需要自己初始化一次。macOS/Linux，在 `backend/` 目录执行，密码至少 12 位：

```bash
read -r -s -p '负责人初始密码（至少12位）: ' OWNER_BOOTSTRAP_PASSWORD
echo
export OWNER_BOOTSTRAP_PASSWORD
export OWNER_BOOTSTRAP_USERNAME=owner
export OWNER_BOOTSTRAP_DISPLAY_NAME=平台负责人
uv run python -m app.bootstrap_owner
unset OWNER_BOOTSTRAP_PASSWORD
```

上述隐藏输入使用 Bash；macOS 默认 zsh 用户可先运行 `bash`，再执行该代码块。PowerShell 在 `backend/` 目录使用：

```powershell
$ownerInitialSecret = Read-Host '负责人初始密码（至少12位）' -AsSecureString
$env:OWNER_BOOTSTRAP_PASSWORD = [System.Net.NetworkCredential]::new('', $ownerInitialSecret).Password
$env:OWNER_BOOTSTRAP_USERNAME='owner'
$env:OWNER_BOOTSTRAP_DISPLAY_NAME='平台负责人'
try {
    uv run python -m app.bootstrap_owner
} finally {
    Remove-Item Env:OWNER_BOOTSTRAP_PASSWORD
    Remove-Variable ownerInitialSecret
}
```

然后按 [项目 README 的原生启动步骤](../README.md) 分别启动 API、Worker 和前端。登录后可查看虚构客户、企业知识和正式关键词库。诊断、文章、监测和发布记录初始为空；本包不把虚构模型结果伪装成真实诊断，也不配置真实渠道账号。

## 维护与验证

- 此包来源于全新隔离 PostgreSQL 的实际迁移结果，未访问原业务数据库。
- SQL 快照用于快速初始化；后续架构变化以 `backend/migrations/` 为准，提交新迁移时同步更新快照、版本与清单。
- 可运行 `uv run --project backend python scripts/verify_database_handoff.py` 独立验证。该命令需要 Docker 和 PostgreSQL 18 镜像，用一次性隔离容器检查迁移、导入、权限、重复导入及 API 登录读取，不接触本机业务库；同事日常使用 SQL 包不要求 Docker。
- 本次实际执行结果见[数据库交接验证记录](VALIDATION.md)。
