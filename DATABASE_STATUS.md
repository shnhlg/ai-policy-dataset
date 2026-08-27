# 数据库状态说明

## 当前包含

`data/database/raw_policy_catalog.db`

这是从 D 盘现存原始附件文件名和文件属性建立的轻量 SQLite 目录数据库，主要用于：

- 核对原始附件是否齐全；
- 按政策编号、来源和文件类型统计；
- 在恢复完整结构化数据后重新关联本地文件；
- 在另一台电脑上进行迁移验证。

它包含两个主要表：

- `raw_files`：每个 PDF/HTML 附件一行；
- `policies`：每个唯一政策编号一行，记录来源和附件数量。

## 当前缺失

以下文件在 D 盘迁移副本中未找到，不能在本包中伪造或替代：

- `viewer/policy_search.db`；
- `data/processed/ai_policies_content_master.csv`；
- `data/processed/policy_fulltexts.jsonl`；
- `data/processed/ai_policies_cleaned.csv`；
- `data/processed/ai_policies_quarantine.csv`；
- `data/processed/ai_policies_manual_review.csv`；
- `data/processed/title_translation_review_2674.csv`；
- `viewer` 下的检索、分类、翻译和 AI 复核代码。

恢复这些文件后，在项目根目录运行：

```powershell
python github_export/ai-policy-dataset/scripts/prepare_full_release.py --project-root .
```

脚本会复制允许发布的数据库、代码和处理结果，不复制 `data/raw` 原始附件。

