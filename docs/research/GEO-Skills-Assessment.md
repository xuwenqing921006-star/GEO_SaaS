# GEO Skills 评估

日期：2026-07-26

## 结论

没有发现可以直接覆盖“中国本地生活企业 GEO 代运营”的成熟单一 Skill。现有能力可以分为三类：

1. 中文自然化改写：可复用 Humanizer-zh 的部分规则。
2. 通用 SEO/GEO 策略：可参考 aaron-marketing-skills 的关键词、内容写作和 GEO 优化模块。
3. 结构化数据与技术可发现性：可参考 marketingskills 的 schema 模块。

不建议首版直接安装完整技能包。公开技能大多以欧美搜索与 AI 平台为中心，并包含与本项目无关的工具约定、未经验证的评分或复杂代理记忆机制。更稳妥的做法是提取方法，形成项目自己的“中国本地服务 GEO 能力链”。

## 候选 Skills

### Humanizer-zh

- 仓库：https://github.com/op7418/Humanizer-zh
- 许可：MIT。
- 适合：识别宣传腔、空泛归因、公式化三段式、过度加粗、破折号滥用、通用积极结尾等明显 AI 写作模式。
- 不适合：GEO 选题、实体建模、关键词研究、来源验证和渠道规划。
- 风险：若机械应用“第一人称、个人观点、允许跑题”等规则，会损害企业事实页、服务说明和知识文章的专业性。
- 采用方式：作为内容流水线最后一道“按内容类型启用的自然化检查”，不允许改写已锁定事实或虚构个人经历。

### aaron-marketing-skills / keyword-research

- 地址：https://github.com/aaron-he-zhu/aaron-marketing-skills/blob/main/seo-geo/survey/keyword-research/SKILL.md
- 可借鉴：搜索意图分类、主题集群、问题型/比较型/操作型 GEO 查询、不能伪造搜索量和难度。
- 需要本地化：加入行政区、商圈、地标、距离、年龄、服务半径和本地决策场景。

### aaron-marketing-skills / content-writer

- 地址：https://github.com/aaron-he-zhu/aaron-marketing-skills/blob/main/seo-geo/implement/content-writer/SKILL.md
- 可借鉴：先证据后写作、新写与更新模式、不能编造指标、按目标意图组织内容。
- 需要本地化：教育、本地生活广告合规，未成年人隐私，中文平台内容形态，以及企业资料事实锁定。

### aaron-marketing-skills / geo-content-optimizer

- 地址：https://github.com/aaron-he-zhu/aaron-marketing-skills/blob/main/seo-geo/implement/geo-content-optimizer/SKILL.md
- 可借鉴：事实密度、可独立引用答案段、实体说明、来源归属、区分“可引用代理指标”和真实 AI 提及。
- 需要本地化：豆包、千问、DeepSeek、百度、微信、抖音等国内来源生态。

### marketingskills / schema

- 地址：https://github.com/coreyhaines31/marketingskills/blob/main/skills/schema/SKILL.md
- 可借鉴：LocalBusiness、Organization、Article、FAQ 等 JSON-LD；结构化数据必须与页面可见内容一致。
- 使用场景：客户官网或平台后续生成可抓取的品牌事实页。

### marketingskills / ai-seo

- 地址：https://github.com/coreyhaines31/marketingskills/blob/main/skills/ai-seo/SKILL.md
- 可借鉴：结构、权威性、外部存在感三层框架，以及“被引用”和“被推荐”不是同一结果。
- 不建议直接采用：包含较多欧美平台假设和需要重新验证的统计数据。

### geo-seo-claude

- 地址：https://github.com/zubair-trabzada/geo-seo-claude
- 可借鉴：网站可抓取性、结构化数据、可引用性和审计报告框架。
- 不建议直接采用：偏 Claude/Linux/Python 审计环境，且不是为国内本地生活场景设计。

## 推荐的项目能力链

首版应将方法拆成以下七个专用能力，而不是一个超大 Skill：

1. **客户事实构建器**：提取企业名称、地址、服务、资质、师资、价格口径、服务区域和证据，处理冲突与缺失。
2. **本地 GEO 查询规划器**：生成地区 × 服务 × 人群 × 意图 × 场景的关键词、问题和主题集群。
3. **内容策略规划器**：根据实体缺口、内容缺口、证据充足度和渠道适配度决定先写什么。
4. **证据约束内容写手**：只使用已确认事实和可靠外部资料生成草稿。
5. **GEO 内容优化器**：提升直接回答能力、事实密度、实体关系、答案段和来源表达。
6. **中文自然化编辑器**：选择性采用 Humanizer-zh，按官网、指南、案例、问答和社交内容使用不同规则。
7. **中国渠道推荐器**：按客户行业和目标 AI 生态推荐官网、地图、本地生活、内容平台、地方媒体和付费渠道。

AI 可见性监测作为独立产品能力，不应混入写作 Skill。

## 首版采用建议

- 现在不安装完整第三方技能包。
- 将 Humanizer-zh 作为可追溯参考，保留 MIT 许可信息。
- 将 keyword-research、content-writer、geo-content-optimizer 和 schema 的有效规则写进产品需求和提示词设计。
- 阶段 C 再决定是否把上述七项能力封装为项目本地 Skills；届时用真实的莱恩美术资料建立测试集，比较启用前后的事实准确率、GEO 结构和人工修改量。

## 验收原则

- 不能捏造企业事实、搜索量、平台收录或 AI 提及。
- 自然化处理不得改变事实含义。
- 所有建议必须说明目标查询、适用渠道、依据和风险。
- 评分必须可解释，不能只给一个神秘总分。
- 不能用虚假榜单、伪造评价或批量低质软文提高所谓 GEO 分数。
