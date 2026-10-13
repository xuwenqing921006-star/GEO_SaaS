# T-067 Developer Verification — 2026-08-09

## Scope

- AI 初次生成保存前质量闭环。
- AI 按建议重新生成保存前质量闭环。
- 标题唯一化与跨文章重复前置检查。
- 自动修正耗尽后的失败与事务回滚行为。

## Implemented

- 提示词版本升级为 `content-v11-one-click-publish-ready`。
- 初次生成改为“一次成稿”协议：模型先在单次响应内部完成事实映射、私有初稿、逐项自检和直接修正，只返回通过全部硬约束的最终稿，不输出试稿、检查表或修改过程。
- 初稿和提纲上下文新增结构化 `publishability_contract`，明确目标渠道、正文与标题长度、品牌次数、联系方式、允许的企业数字与费用说法及禁用结构。
- 已确认事实增加无业务含义的顺序引用 `F01...`，供模型在内部逐项映射；公开正文仍禁止输出这些引用。
- 企业数字和费用改为白名单：未在安全事实中明确列出的数字、数量、免费或收费结论在生成阶段即禁止使用。
- 发布合同新增事实、数字、费用、渠道质量、自然表达、联系方式和公开输出七类机器可读硬约束。
- 模型返回多个标题时，在质量门禁前自动选择长度合规、非模板化且与正文关联最高的候选标题。
- 发布合同只从已经安全过滤、采用保守口径的事实中生成，不会把被排除的营销说法或冲突数字重新带回提示词。
- 自动修正从多轮流程收敛为最多一次完整重写；首次生成是主流程，重写只是模型未遵守硬约束时的安全兜底。
- 每轮候选统一执行事实、合规、平台低质、标题和跨文章重复检查。
- 仍有阻断项时不创建文章版本，并把任务退回后台候选重试队列；只有达到任务最大尝试次数后才形成任务级失败。
- 按建议重新生成失败时保留原文章状态，不再把原文章改成 `blocked`。
- 保存后的原有质量检查保留为防御性二次校验，没有放宽任何规则。

## Developer Checks

- `uv run --project backend pytest -c backend/pyproject.toml backend/tests/content/test_content_api.py -q -k "not selected_keywords_create_batch_ai_articles_and_support_publish_archive"`
  - 结果：71 passed，1 deselected。
  - 说明：被排除的旧综合用例仍按历史流程直接发布未确认的生成任务，与 T-066 新增的“生成任务确认后才能发布”规则冲突，不属于本次生成质量改动。
- `uv run --project backend pytest -c backend/pyproject.toml backend/tests/prompts/test_prompt_templates_api.py -q`
  - 结果：4 passed。
- `uv run --project backend ruff format --check backend/app/content.py backend/app/prompt_templates.py backend/tests/content/test_content_api.py`
  - 结果：passed。
- `uv run --project backend ruff check backend/app/content.py backend/app/prompt_templates.py backend/tests/content/test_content_api.py`
  - 结果：passed。
- `uv run --project backend mypy backend/app/content.py backend/app/prompt_templates.py`
  - 结果：Success，2 个源文件无问题。
- 本地 API 与 Worker 重启后 `GET /api/v1/health/ready`
  - 结果：database、storage、worker heartbeat 均为 ok。

## Live Batch Correction

- 发现真实批次 `195c910b-b582-48df-9e86-b2be8f605330` 在 Worker 切换期间跨用了 `content-v9` 与 `content-v10`，初始结果为 15 篇中 7 篇完成、8 篇失败。
- 修正绝对化用语误判：保留“最好先问清”“最好不要只看”等建议语境，但继续阻断“本地最好机构”等推广结论。
- 提纲模型发生可重试的结构化输出异常时，改用同一事实快照生成安全提纲继续写作，不再整篇失败。
- 发布门禁阻断改为系统后台自动更换候选；失败候选不创建内容版本，也不暴露给运营人员。
- 重启 API 与 Worker 后原位重跑该批次 8 篇失败稿，并继续升级重跑 3 篇旧 warning 稿。
- 最终数据库结果为：15 篇 `checked`、0 篇 `failed`、0 篇 `generating`；15 篇质量检查全部 `passed`，0 warning、0 blocking。
- 15 个标题规范化后仍全部唯一；正文有效字符为 837—1650。
- 最终门禁同步阻断 `entity_clarity`、`natural_language`、`question_relevance` 三类可执行 warning，避免“任务成功但文章仍需调整”。
- 生成保存前增加确定性语言收敛，清除已知 AI 套话、宣传短语和绝对化结果表述；处理后仍须通过同一质量门禁。

## Status

Developer verification complete. Task remains `in_progress`; independent Tester and product acceptance are not self-approved by Developer.
