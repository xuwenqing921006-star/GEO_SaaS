# T-006 真实认证、客户与工作台边界

## 目标

把 P00/P01 从开发 Mock 切换为服务端真实接口：单负责人登录、服务端 Session、
CSRF、防暴力破解、改密、客户生命周期、乐观锁和工作台摘要。

## 架构决定

- 使用现有 FastAPI、SQLAlchemy Async、PostgreSQL 和 Alembic，不引入外部认证平台。
- 密码使用 `pwdlib[argon2]` 的推荐 Argon2id 配置；数据库只保存哈希。
- Cookie 只保存高熵随机 Session 令牌，数据库仅保存令牌 SHA-256 摘要。
- `geo_session` 设置 HttpOnly、SameSite=Lax；生产环境强制 Secure。
- 写请求同时校验 Session 和 `X-CSRF-Token`，CSRF 数据同样只以摘要形式保存。
- Session 12 小时无操作过期、7 天绝对过期；Session 绑定负责人认证版本，
  改密递增版本并撤销全部 Session，并发旧密码登录也会立即失效。
- 登录按可信代理还原的客户端地址做有界、并发原子短窗口限流；用户名不存在与密码错误
  返回同一文案。API 不直接暴露端口，Nginx 覆写外部转发地址。
- 客户更新使用单条 `UPDATE ... WHERE version ... RETURNING` 原子乐观锁；
  不存在或越界资源统一返回 404，不允许通过普通编辑绕过归档恢复。

## 数据与迁移

- `0002` 新增 `owners`、`owner_sessions`、`clients` 三张表；`0003` 在兼容旧
  `0002` 数据库的前提下增加单负责人、认证版本和客户规范名称约束。
- 负责人账号通过受保护的运维初始化流程写入，不提供注册、邀请、OAuth 或客户登录接口。
- 数据库通过固定 singleton 键强制只存在一个负责人；客户标准名称经 NFKC、大小写和空白
  规范化后保持唯一。
- 客户归档保留数据，恢复只改变状态并递增版本。

## 兼容、回滚与运维

- 现有 `VITE_USE_MOCK=true` 演示保留；正式构建继续排除 Mock。
- 回滚应用版本不会删除新表；数据库降级仅在确认无数据保留要求时执行。
- 日志不得记录密码、Cookie、CSRF 或请求体；错误响应保持统一信封。

## 验收

- 后端认证、CSRF、限流、客户生命周期和版本冲突测试通过。
- `VITE_USE_MOCK=false` 的 P00/P01 Web 流程通过。
- 无注册、多角色、邀请、OAuth 或客户登录路由。
