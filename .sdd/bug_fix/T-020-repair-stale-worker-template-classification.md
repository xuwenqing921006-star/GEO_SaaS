# T-020 修复旧 Worker 造成的模板知识分类异常

## 问题

- 环境：本地真实 API 与后台资料处理进程。
- 客户：青岛莱恩美术教育。
- 实际行为：客户模板生成的 21 条知识全部被旧处理进程归类为“服务产品”。
- 期望行为：企业信息、地区范围、服务产品、服务对象、价格、流程、企业优势、联系信息和补充说明按模板字段分别归类。
- 影响：知识结构统计失真，诊断、关键词建议和 AI 内容取材可能无法识别联系方式、团队优势等结构化信息。
- 严重度：高。

## 根因

本地 Worker 在模板结构化分类代码更新前启动，开发过程没有自动重启。更新后上传的资料仍由旧进程使用 `other -> service` 兜底逻辑处理。

旧逻辑还会优先按值内部的全角冒号拆分普通候选内容，导致 5 条知识的业务前缀
被截掉。原始 `material_fragments` 未受影响。

## 修复范围

- 安全停止旧 API 与 Worker，使用项目启动脚本重新启动。
- 仅修正目标客户、目标资料产生的 21 条派生知识的分类、规范 key 和标题。
- 从原始 fragment 恢复 5 条被旧 Worker 截断的 Fact.value 和 Evidence.quote。
- 保留 Fact ID、Evidence ID、来源关系和客户资料文件。
- 验证所有模板字段均有且只有一个规范 key，并验证服务健康和真实页面分类。

## 解决结果

- 21 条 Fact 原位修复完成，分类分布为 identity 5、location 3、service 4、
  audience 1、price 1、process 1、capability 2、contact 3、restriction 1。
- 21 个 canonical key 全部唯一，不再存在旧候选 key。
- Fact.value、Evidence.quote 与 21 个原始 fragment 全部一致。
- Fact ID 哈希与 FactEvidence 关系哈希在原文恢复前后保持不变。
- API live/ready 均为 HTTP 200，数据库、存储和 Worker heartbeat 均为 `ok`。
- 真实知识库页面显示 21 条知识和 9 个分类，“服务产品”仅 4 条。
- 增加模板值内部包含全角冒号的回归测试，防止再次截断。

详细事务前置条件、行数断言和哈希见
`.sdd/evidence/T-020-data-repair.md`。
