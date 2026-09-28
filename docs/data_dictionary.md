# AI 政策数据字典（初版）

`policies.csv` 的每一行代表一项已成功获取官方来源的独立政策文件。

| 字段 | 含义 |
|---|---|
| `policy_id` | 稳定的人工分配ID；不同版本未来由关联表管理。 |
| `title_original` | 官方原文标题。 |
| `title_zh` | 统一的中文标题。 |
| `country_or_org` | 国家、地区或国际组织。 |
| `jurisdiction_level` | national、subnational、supranational 或 international。 |
| `issuer` | 发布机构。 |
| `policy_type` | 法规、战略、指南、框架、指令等。 |
| `legal_status` | 现行、草案、已撤销、已废止或待核验。 |
| `published_date` | 官方发布日期，ISO 8601。 |
| `language` | 原文语言。 |
| `topics` | 分号分隔的主题标签。 |
| `official_url` | 手工登记的官方来源。 |
| `official_url_final` | 抓取时最终落地URL。 |
| `content_sha256` | 原始响应内容哈希，用于精确去重。 |
| `raw_file` | 本地原始响应文件。 |
| `verification_status` | `verified_http` 表示抓取时取得2xx响应。 |
| `text_preview` | HTML页面的首段清洗文本，仅用于人工快速检查。 |

原始文件仅作为研究可追溯缓存；后续公开再分发前，应逐条检查对应来源的许可条件。

## 内容增强字段

`ai_policies_enriched.csv` 在主表基础上增加以下字段，全部保持官方原文语言；不生成机器翻译。

| 字段 | 含义 |
|---|---|
| `content_summary_original` | 由目标或措施原文关键句组成的简短概览。 |
| `policy_objectives` | 与政策目标相关的原文关键句。 |
| `policy_measures` | 与执行措施相关的原文关键句。 |
| `regulatory_requirements` | 与义务、禁止、备案、评估或合规有关的原文关键句。 |
| `target_entities` | 适用对象相关的原文关键句。 |
| `sectors_extracted` | 从正文识别的行业标签。 |
| `technologies_extracted` | 从正文识别的技术标签。 |
| `fulltext_record_id` | 对应 `policy_fulltexts.jsonl` 中的全文记录。 |
| `fulltext_char_count` | 抽取后正文长度。 |
| `content_extraction_status` | `extracted` 或 `extraction_failed`。 |
