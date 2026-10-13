# T-055 四平台联网搜索与来源证据研究

## 结论

| 平台 | 官方 API 路径 | 联网与来源能力 | 本任务处理 |
|---|---|---|---|
| 通义千问 | 阿里云百炼 | 支持联网搜索；DashScope 返回 `search_info.search_results`，可开启引用角标 | 使用原生 DashScope 搜索请求并保存来源 |
| 文心一言 | 百度千帆 `v2/chat/completions` | ERNIE 支持 `web_search`，返回 `search_results` | 新增配置与来源解析 |
| 豆包 | 火山方舟 `api/v3/responses` | Responses API 支持 `web_search`，可配置公开网页、头条、抖音等来源 | 诊断改用 Responses API 并读取引用 URL |
| DeepSeek | DeepSeek `chat/completions` | 官方对话 API 文档当前只有对话、工具调用等字段，没有原生网页搜索结果字段 | 保留回答检测，来源状态标记为不支持 |

## 官方资料

1. 阿里云百炼《大模型如何联网搜索》：`enable_source: true` 后，响应的 `search_info`
   包含搜索结果；`enable_citation: true` 可在回答中生成引用角标。
   https://help.aliyun.com/zh/model-studio/web-search
2. 百度千帆《联网搜索》：ERNIE 请求可添加 `web_search`；示例返回顶层
   `search_results`，包含索引、URL 和标题。
   https://cloud.baidu.com/doc/qianfan-docs/s/Wm8r4sw29
3. 百度千帆《快速开始》：OpenAI 兼容 Base URL 为
   `https://qianfan.baidubce.com/v2`，使用 Bearer API Key。
   https://cloud.baidu.com/doc/qianfan-docs/s/qm8qxemze
4. 火山方舟《Web Search（联网内容插件）》：Responses API 的工具类型为 `web_search`；
   官方示例使用 `/api/v3/responses`。
   https://www.volcengine.com/docs/82379/1756990?lang=zh
5. 火山方舟《联网系列插件升级说明》：公开网页、头条图文、抖音百科等为可选搜索资源；
   来源资源可能单独计费。
   https://www.volcengine.com/docs/82379/1359519
6. DeepSeek《对话补全》与《模型与价格》：当前官方响应结构未定义搜索结果或网页来源字段。
   https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/
   https://api-docs.deepseek.com/zh-cn/quick_start/pricing

## 风险与约束

- 云厂商 API 与消费者 App 的检索索引、排序策略、账号状态和灰度能力可能不同。
- 联网来源会随时间、地区、模型版本和搜索插件配置变化，因此每次诊断都保存检测时间、
  模型和来源样本。
- 火山方舟 Web Search 可能产生插件费用；沿用每日预算门禁。
- 只有来源 URL 或官方来源数组才能进入渠道信号；模型正文中没有 URL 的“据悉”不算证据。

