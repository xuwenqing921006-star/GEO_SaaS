# T-018 代码复审

## 结论

PASS。独立 Reviewer 最终复审未发现开放阻断项，且未修改交付文件。

## 重点复核

- 企业所在地使用 `location.administrative_area`，实际服务范围使用 `location.service_area`；诊断只读取真实服务范围。
- 简版客户资料模板能生成结构化企业、地区、服务、受众与联系方式知识条目。
- 模板重导入进入客户事实集锁，并对已有 Fact 行加锁，避免覆盖竞态。
- 已确认条目被模板更新后回退为 `client_provided`，同时清除旧 `confirmation_note`。
- 旧 restricted / not_authorized 证据不会进入内容上下文。
- 前端会读取资料和知识条目的全部分页。
- 企业知识库页面已移除审核式功能和额外 GEO 诊断入口。

## 独立检查

- 聚焦复跑：8 项通过。
- PostgreSQL 专项锁测试因本地没有 `TEST_POSTGRES_DATABASE_URL` 跳过；Reviewer 对锁顺序和调用位置完成静态复核。
