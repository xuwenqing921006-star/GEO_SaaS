# T-070 Developer Verification

- 日期：2026-08-10
- 任务：头条号低质治理与发布保护
- 结论：开发实现与开发侧定向验证完成；依据项目规则，任务保持 `in_progress`，等待独立 Tester 与产品验收。

## 实现范围

- 头条号平台生成规范增加批量同质、纯广告、转化、联系方式、品牌次数、有效内容部分和作品声明约束。
- 头条号提示词要求正文至少 85% 用于读者价值，企业标准名称最多自然出现 2 次。
- 确定性门禁新增诱导夸张标题、有效内容部分不足、直接转化、促销优惠、软文推介和企业句子占比检查。
- 真实发布增加同一头条账号至少间隔 3 小时、滚动 24 小时最多提交 2 篇的保守保护；固定模拟环境不启用该保护。
- 内容提示词版本升级为 `content-v12-toutiao-quality`，质量规则版本升级为 `deterministic-v5-toutiao-quality`。

## 验证证据

1. `uv run --project backend pytest -c backend/pyproject.toml backend/tests/publishing/test_publishing_specs.py backend/tests/publishing/test_publishing_session_health.py backend/tests/publishing/test_publication_preflight.py backend/tests/content/test_content_api.py -q`
   - 结果：95 passed，1 个第三方 Starlette/httpx 弃用警告。
2. `uv run --project backend ruff format --check ...`
   - 结果：7 files already formatted。
3. `uv run --project backend ruff check ...`
   - 结果：All checks passed。
4. `uv run --project backend mypy backend/app/content.py backend/app/prompt_templates.py backend/app/publishing.py backend/app/publishing_specs.py`
   - 结果：Success，4 个源文件无类型问题。

## 边界

- 本次没有调用付费模型生成真实文章，也没有向头条号执行真实发布。
- 3 小时和 24 小时限制是可逆的产品保护策略，不是今日头条公开的官方安全阈值。
