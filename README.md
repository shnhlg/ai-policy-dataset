# 国内外人工智能政策数据集

## 完整数据集在哪 / Where Is the Full Dataset

完整数据集（结构化主库、全文正文、检索数据库、中文官方库、原始附件等，约 11 GB）托管在 Hugging Face：

- https://huggingface.co/datasets/LinkwiseSH/ai-policy-dataset
- 国内镜像 / China mirror: https://hf-mirror.com/datasets/LinkwiseSH/ai-policy-dataset

The full dataset (structured tables, full texts, search database, official Chinese library, raw attachments, ~11 GB) is hosted on Hugging Face at the links above. This repository contains the code / lightweight package; download the dataset from Hugging Face to run the search window.

本仓库用于管理人工智能政策数据集的数据库、检索程序、清洗与翻译代码，以及跨电脑恢复和验证脚本。

## 当前发布包状态

本发布包从 `D:\codex\公开数据数据集` 生成。迁移后的 D 盘副本目前包含政策原始附件，但没有找到此前生成的以下成果：

- `viewer/policy_search.db`：全文检索数据库；
- `viewer/`：可视化检索窗口及索引代码；
- `data/processed/`：结构化主库、清洗库、隔离库、待人工复核库和正文 JSONL；
- 标题翻译缓存、AI 复核缓存及相关运行脚本。

因此，本包暂时属于**可上传、可验证、但待补全的 GitHub 发布包**。`data/database/raw_policy_catalog.db` 是根据 D 盘现存原始附件重新建立的目录数据库，不是原来的全文检索数据库。

## 已完成成果统计

根据此前已经完成并核验的成果：

| 指标 | 数量 |
| --- | ---: |
| 结构化总记录 | 10,542 |
| 清洗后相关 | 2,739 |
| AI 复核无关并隔离 | 6,874 |
| 待人工复核 | 929 |
| 完成上下文译审的非中文标题 | 2,674 |

原始记录在清洗过程中不删除，采用清洗库、隔离库和待人工复核库三层输出。

## 当前 D 盘原始附件盘点

| 指标 | 数量 |
| --- | ---: |
| 政策附件文件 | 19,699 |
| 唯一政策编号 | 19,528 |
| PDF | 17,828 |
| HTML | 1,871 |
| 总体积 | 约 11.36 GB |

附件数不等于政策记录数。同一政策编号可能存在多个抓取版本或关联文件。

## 目录

```text
ai-policy-dataset/
├─ data/
│  └─ database/
│     └─ raw_policy_catalog.db   # 原始附件目录数据库
├─ scripts/
│  ├─ build_raw_catalog.py      # 从 data/raw 重建目录数据库
│  ├─ verify_release.py         # 发布包完整性与敏感信息检查
│  ├─ prepare_full_release.py   # 检测并复制恢复后的完整数据库与代码
│  └─ bootstrap_windows.ps1     # 另一台 Windows 电脑的初始化提示
├─ .gitattributes               # Git LFS 规则
├─ .gitignore
├─ DATABASE_STATUS.md
└─ README.md
```

## 在另一台电脑上传 GitHub

1. 安装 Git 或 GitHub Desktop，并安装/启用 Git LFS。
2. 解压发布包并进入 `ai-policy-dataset` 目录。
3. 运行：

```powershell
git lfs install
git init
git add .
git commit -m "Initial AI policy dataset release"
git branch -M main
git remote add origin https://github.com/<账户>/<仓库>.git
git push -u origin main
```

4. 上传前运行完整性检查：

```powershell
python scripts/verify_release.py
```

## 大文件策略

普通 GitHub 仓库会阻止超过 100 MiB 的单个文件。本包已通过 `.gitattributes` 将 SQLite 数据库和压缩数据文件交给 Git LFS。原始 PDF/HTML 不进入 Git 仓库；建议作为独立备份、对象存储或分卷 Release 资产保存。

## 安全要求

- 不提交 `.env`、API Key、浏览器 Cookie、代理凭据或本机绝对路径配置。
- `OPENAI_API_KEY`、`OPENAI_BASE_URL` 等只能通过环境变量或本地 `.env` 提供。
- 上传前必须运行 `verify_release.py`。

## 数据使用说明

AI 分类、摘要和中文译文用于检索与研究辅助，不构成法律意见或官方译文。正式引用前应回查政策官方链接与原始文件。

