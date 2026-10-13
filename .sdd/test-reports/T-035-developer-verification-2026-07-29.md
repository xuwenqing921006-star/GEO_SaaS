# T-035 Developer Verification — 2026-07-29

状态：开发验证完成，等待独立 Tester 与产品验收。

## 自动化验证

- 后端 content、prompts、providers、monitoring 定向回归：68 passed。
- Ruff：passed。
- Mypy：passed。
- 前端单元测试：62 passed。
- Prettier、ESLint、Vue TypeScript：passed。
- 前端生产构建：passed。
- ECC V2 doctor：passed。

## 真实运行验证

- 本地 API、数据库、存储和 Worker heartbeat 均为 ready/ok。
- 代表文章文档：`3711754f-d771-4d4a-9e39-d6ad803c78ff`。
- 最新文章版本：v4，`regenerated`。
- 写作模型：DeepSeek `deepseek-v4-pro`。
- 提示词协议：`content-v3`。
- 内容形式：`local_recommendation`。
- 目标渠道：`toutiao`。
- 当前提示词快照包含：
  - 内容安全保护层 v2；
  - 文章通用写作规则 v2；
  - 本地推荐解答 v1；
  - 头条号渠道规则 v2；
  - 人工修改建议 v1。
- 最新发布检查：`passed`，provider=`rules`，
  model=`lightweight-publish-check-v1`，问题数 0。
- 本次真实重新生成调用 DeepSeek；未调用千问。

## 安全说明

- 报告未记录 API Key、数据库密码、Cookie 或文章中的个人联系方式。
- 真实模型调用只使用当前客户已录入、用于文章生成的企业资料。
- Developer 未将任务标记为 passed。
