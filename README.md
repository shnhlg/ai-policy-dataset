# 全球 AI 政策数据集

## 完整数据集在哪 / Where Is the Full Dataset

完整数据集（结构化主库、全文正文、检索数据库、中文官方库、原始附件等，约 11 GB）托管在 Hugging Face：

- https://huggingface.co/datasets/LinkwiseSH/ai-policy-dataset
- 国内镜像 / China mirror: https://hf-mirror.com/datasets/LinkwiseSH/ai-policy-dataset

The full dataset (structured tables, full texts, search database, official Chinese library, raw attachments, ~11 GB) is hosted on Hugging Face at the links above. This repository contains the code / lightweight package; download the dataset from Hugging Face to run the search window.

> 已恢复原版网页、10,542 条检索记录、完整正文、翻译与分类结果。双击 `start.bat` 启动。下方是早期采集阶段的历史说明，不代表当前数据量；不要为了查看数据重新运行采集或翻译。

本项目从公开、官方来源采集国内外 AI 相关政策，并保留来源、抓取时间、原始文件哈希与版本线索。政策标题、摘要、摘录和全文均保持官方原始语言。当前处于第一批种子采集阶段，目标是形成可扩展至 10,000+ 条的持续更新数据集。

## 快速开始

```powershell
python src/collect_seeds.py
python src/validate_dataset.py
python src/discover_index_candidates.py
python src/ingest_beijing_candidates.py
python src/build_master_dataset.py
python src/validate_dataset.py
python src/report_status.py
python src/enrich_policy_content.py
python src/collect_govuk.py --limit 100
```

输出文件位于 `data/processed/`：

- `policies.csv`：成功抓取并验证的政策条目
- `failed_fetches.csv`：需要后续检查的失败来源
- `collection_summary.json`：本次运行摘要
- `policy_candidates.csv`：从官方专题目录发现、待人工规则复核的候选项
- `beijing_policies.csv`：已由北京官方政策页验证的地方政策
- `ai_policies_master.csv`：已去重的主数据集
- `master_excluded_incomplete.csv`：官方页面可访问但关键字段待补全的记录，不计入主数据集
- `status_report.json`：主数据集的数量、覆盖和待处理项摘要
- `ai_policies_enriched.csv`：增加政策摘要、目标、措施、监管要求等内容字段的主表
- `ai_policies_content_master.csv`：正文成功提取、可直接用于内容分析的政策主表
- `content_extraction_failures.csv`：目录已验证但正文尚未获取的记录，不计入内容主表
- `policy_fulltexts.jsonl`：与主表按 `policy_id` 关联的完整正文

## 采集原则

- 只有官方来源的独立政策文件进入主数据集。
- 聚合平台只用于发现线索，不能替代原始发布页面。
- 同一政策的转载、镜像和多语言版本不重复计数。
- 不绕过验证码、登录、robots 限制或访问控制。
- 每个站点按低频率访问，并保存抓取状态以便增量更新。

## 下一阶段

1. 从中国中央及地方政策专题页发现候选记录。
2. 接入欧盟、美国、英国、加拿大、日本、新加坡等官方目录。
3. 增加版本关系、近似去重、全文解析与多语言摘要。
4. 以 200、1,000、2,000、5,000、10,000 条为质量验收节点。
## Docker 运行（可选）

本项目自带容器化启动，不需要在宿主机安装 Python：

```powershell
docker compose up -d --build
```

浏览器打开 http://127.0.0.1:8765 。常用命令：`docker compose logs -f ai-policy-viewer` 看日志，`docker compose down` 停止。

注意：仓库不包含大数据文件（正文 JSONL、`viewer/policy_search.db`、原始附件等），容器通过挂载本目录运行；请在完整恢复包目录内执行上面的命令。
