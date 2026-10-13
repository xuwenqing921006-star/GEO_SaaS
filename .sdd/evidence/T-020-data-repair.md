# T-020 数据修复审计证据

## 修复对象

- 客户 ID：`c05353e3-9698-4ef7-87f1-58d89fbbf5fe`
- 资料 ID：`132a223e-61cb-4656-902e-9b01dce04a8b`
- 修复范围：该资料产生的 21 条 Fact、21 条 Evidence 和既有 FactEvidence 关系。

## 分类修复前快照

- Fact 数量：21。
- 分类：21 条均为 `service`。
- Fact ID + value 有序哈希：`b6003bba87bcf04651f234f15fbceaec`。
- FactEvidence 关系有序哈希：`4862de2c07844be6ae5e663f56bf2c9d`。
- 资料原始片段：21，处理状态 `succeeded`。

## 分类修复事务

事务在写入前断言：

- 目标资料恰好产生 21 条旧候选 Fact；
- 21 个模板字段均能映射到唯一 canonical key；
- 目标客户不存在 canonical key 冲突；
- 目标 Fact 恰好具有 21 条来源关系。

事务原位更新 21 条 Fact 的 `category`、`key`、`label`、状态和置信度，
未删除或新建 Fact、Evidence、FactEvidence，也未修改 Fact.value。

分类修复后：

- Fact ID + value 有序哈希仍为 `b6003bba87bcf04651f234f15fbceaec`。
- FactEvidence 关系有序哈希仍为 `4862de2c07844be6ae5e663f56bf2c9d`。
- 分类分布为 identity 5、location 3、service 4、audience 1、price 1、
  process 1、capability 2、contact 3、restriction 1。
- canonical key 为 21/21 唯一，不再存在 `material.*.candidate.*` key。

## 原文完整性复查与恢复

Reviewer 将最终 Fact.value、Evidence.quote 与 21 个 material fragment 比对，
发现旧 Worker 在首次导入时因值内部的全角冒号截掉 5 个前缀。原始 fragment
保持完整。

恢复前审计：

- Fact ID 有序哈希：`79c1fc49757e71c9c7b0767fbc5b0863`。
- FactEvidence 关系有序哈希：`4862de2c07844be6ae5e663f56bf2c9d`。
- 原始 fragment 有序哈希：`66f3e19ec88290574b2597fdbe78f1b9`。
- 与原始 fragment 不一致：5 条。

恢复事务在写入前断言：

- 21 个 `geo_template` fragment 均存在且非空；
- 21 个 canonical key 均能唯一映射到目标 Fact；
- 目标资料恰好有 21 条 Evidence 关系；
- 仅 5 条 Fact.value 与原始 fragment 不一致。

事务原位恢复 5 条 Fact.value 和对应 5 条 Evidence.quote，并断言实际更新行数
分别为 5。事务提交前再次断言 Fact.value、Evidence.quote 与原始 fragment
不一致数为 0。

恢复后审计：

- Fact 数量：21。
- Fact ID 有序哈希仍为 `79c1fc49757e71c9c7b0767fbc5b0863`。
- FactEvidence 关系有序哈希仍为 `4862de2c07844be6ae5e663f56bf2c9d`。
- canonical key：21/21 唯一。
- 与原始 fragment 不一致：0。

## 运行状态

- 旧 API、Worker 已停止。
- API 与 Worker 均使用项目启动脚本和当前代码重新启动。
- `/api/v1/health/live`：HTTP 200。
- `/api/v1/health/ready`：HTTP 200，database、storage、worker heartbeat 均为
  `ok`。
