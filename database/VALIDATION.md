# 数据库交接验证记录

日期：2026-10-15。范围：表结构快照、全新虚构演示数据、权限脚本和导入说明；没有修改业务代码或历史业务任务状态。

## 隔离 PostgreSQL 18 验证

执行：`uv run --project backend python scripts/verify_database_handoff.py`。

验证脚本创建专用临时容器和两个空库，结束后移除自己的容器。未连接、启动或导出原业务数据库。

| 检查 | 结果 |
| --- | --- |
| 从空库执行全部 29 个 Alembic 迁移 | 通过，版本 `0029` |
| 在另一空库事务导入 schema、demo、grants | 通过，41 张业务表及 1 张版本表 |
| 比对实际迁移与 SQL 导入后的完整结构 | 通过；仅归一化 PostgreSQL 回读时等价改写的字符串数组类型转换 |
| 演示数据行数 | 通过，2 客户、12 知识、12 证据、12 关联、2 画像、2 策略、6 关键词 |
| 负责人、会话、模型配置、发布账号、发布记录、文件、任务、用量表初始为空 | 通过 |
| 重复导入演示数据与权限 | 通过，已有记录保留、行数不增加 |
| 向非空库再次导入结构 | 按预期拒绝 |
| 运行角色读取、更新及禁止建表 | 通过 |
| 导入后再执行 `alembic upgrade head` | 通过，无需重放历史迁移 |
| 临时负责人初始化、API 登录、客户列表及两家客户的知识/画像/策略/关键词工作台读取 | 通过，接口全部返回 200 |

临时负责人密码由验证脚本随机生成，仅用于隔离测试库，不随 SQL 提供。

## 文件与静态检查

- `ruff check`、`ruff format --check`：通过，使用后端配置检查新增验证脚本。
- `mypy --config-file backend/pyproject.toml backend/app scripts/verify_database_handoff.py`：通过，36 个源文件。
- `node --test scripts/workspace.test.mjs`：4/4 通过。
- 三个 SQL 文件的 SHA-256 与 `manifest.json` 一致；SQL 使用 LF，克隆后可直接核对。
- 新增及相关交接文档的本地链接有效；新增说明中的 Bash 和 3 个 PowerShell 代码块通过语法检查。
- 251 个原业务文件与既有基线 SHA-256 一致，65 个原业务任务对象保持不变。
- 新增演示 INSERT 仅涉及清单中的 7 张表；候选提交未包含本机真实环境密钥或凭据。

## 验证边界

本次验证使用一次性 PostgreSQL 18 容器；没有在同事电脑上安装原生 PostgreSQL，也没有执行浏览器全流程、真实模型调用或渠道发布。Starlette TestClient 有上游 httpx 弃用提示，不影响本次通过结果。原 API、Worker、前端和业务数据库保持停止。
