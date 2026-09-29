# AI 政策资料库

用于检索、筛选和阅读各国及国际组织发布的 AI 政策资料。保留原文标题、发布机构、日期、官方来源、正文提取状态和审核记录。

当前验收版本收录 10,547 条记录，其中 2,744 条标记为 AI 相关。并非所有记录都有可用正文或原件；页面会分别标注。搜索覆盖标题、机构、主题和摘要，尚不检索完整正文。

## 数据文件

代码和轻量补充材料在 GitHub，完整数据包在 [Hugging Face](https://huggingface.co/datasets/LinkwiseSH/ai-policy-dataset)（[国内镜像](https://hf-mirror.com/datasets/LinkwiseSH/ai-policy-dataset)）。代码、在线服务和下载数据包分别更新，使用时请核对各自版本。

启动前，目录至少需要：

```text
data/processed/ai_policies_content_master.csv
data/processed/policy_fulltexts.jsonl
```

原始附件放在 `data/raw/` 或 `data/official_zh/raw/`。缺少原件不会阻止启动，但相应记录不会显示可用下载入口。若克隆后得到 Git LFS 指针文件，需要先运行 `git lfs pull` 下载仓库内的 LFS 文件；这不会自动下载外部完整数据包。

`dataset_manifest.json` 记录本次验收的数据数量和 SHA256。若下载的数据包与之不同，验证工具会明确报错，不会自动修改或补造记录。

## Docker 启动

```powershell
docker compose up -d --build
```

打开 [本机检索页](http://127.0.0.1:8765)。首次启动需要复制运行数据并建立索引，请用 `docker compose logs -f ai-policy-viewer` 查看进度。

应用代码打入镜像，数据源以只读方式挂载。SQLite 和正文运行副本存放在 Docker 的 `policy-runtime` 命名卷，不再直接在 Windows 项目挂载上执行数据库查询。镜像固定 Python 基础版本及摘要，索引在运行环境构建并检查 FTS 完整性。

后续启动会复用未变化的数据版本。原始数据或索引构建代码变化时，先生成独立版本，验证完成后才切换；旧版本保留在卷内。`docker compose down` 不会删除数据卷。**不要使用 `down -v` 清理运行数据。**

更新时可先准备新版本，成功后再重建服务容器，缩短停机时间：

```powershell
docker compose build
docker compose run --rm --no-deps ai-policy-viewer python scripts/prepare_runtime.py
docker compose up -d
```

健康状态：`docker compose ps`。健康接口：[本机健康检查](http://127.0.0.1:8765/health)。服务默认仅对本机开放。

公网访问可通过反向代理或隧道连接该端口。网页文案面向在线读者；HTML、CSS、JavaScript 支持 gzip 与 ETag 校验，刷新未变化的资源返回 304。较大的 JSON 响应也支持 gzip，接口仍实时读取当前运行版本。PDF 保留分段读取，避免先下载完整文件再阅读。

## 验证

```powershell
docker compose run --rm --no-deps ai-policy-viewer python scripts/test_runtime.py
docker compose run --rm --no-deps ai-policy-viewer python scripts/verify_restore.py
```

第一条运行接口与回归测试；第二条核对源文件哈希、唯一编号、每条正文的位置与字数、隔离状态和 FTS 完整性。原件未提供会计入缺失数量，不会被当作“有 PDF”。

不使用 Docker 时，可运行 `python scripts/launch.py` 或双击 `start.bat`。需要 Python 3.11+ 和支持 FTS5 trigram 的 SQLite；初次运行或版本变化会重建本地索引。测试前先完成索引构建，再运行 `python -m unittest discover -s tests -v`。

## 界面中的状态

- **正文已提取**：存在提取文本，不等于已经逐条确认法规效力或法律性质。
- **非正文 / 混合文档**：保留目录记录，隔离正文，等待修复或拆分。
- **正文待 OCR**：没有可检索文本；如果 PDF 存在，仍可打开原件。
- **摘要含网页导航**：暂不展示该摘要，原始提取结果保留在折叠的审核记录中。
- **可查看 PDF / 其他原件**：当前数据包确实能访问到文件。

筛选选项括号内为全库数量，结果区显示当前条件的匹配数量。国家和语言的常见同义标签在检索索引中合并，源 CSV 的原始值保留。检索条件保存在页面 URL，可复制链接或使用浏览器前进、后退。

## 更新数据与回退

不要为“打开资料库”重跑采集、翻译和模型审查脚本。它们是维护工具，不是启动步骤。

`src/enrich_policy_content.py` 默认把新结果写到 `data/staging/` 的独立目录，不覆盖当前正文库。提取超出页数限制的 PDF 会明确失败，不把截断文本标成完整提取。审核新输出后，应在停止发布操作的情况下成套替换 CSV 和 JSONL，再准备运行版本。

`scripts/normalize_csv_headers.py <CSV路径>` 仅在重复列的每一行内容都一致时合并列；有冲突立即中止。

运行卷的 `releases/<版本号>/ready.json` 记录输入哈希、SQLite 版本和记录数量，`CURRENT` 记录最近准备完成的版本。需要回退时，在 `.env` 设置 `AI_POLICY_RELEASE=<已存在的20位版本号>` 并重新运行 `docker compose up -d`；同时使用与该数据版本匹配的代码镜像。完成回退后不要直接删除旧版本。

## 项目目录

| 目录 | 内容 |
|---|---|
| `viewer/` | 检索服务、索引构建、页面和标题译文 |
| `src/` | 来源采集、内容提取和结构化处理 |
| `scripts/` | 启动、运行版本准备、验证和数据维护工具 |
| `tests/` | 接口、文件访问与数据状态回归测试 |
| `data/official_zh/` | 中文官方来源的补充资料 |
| `docs/` | 字段与历史处理说明 |

旧的迁移清单用于对应历史恢复包；当前验证以 `dataset_manifest.json` 为准。模型审核是辅助标注，不应代替官方文本核对或人工判断。
