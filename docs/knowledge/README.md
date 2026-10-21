# CygnusX 知识库目录

`docs/knowledge/` 是领域知识库与平台帮助文档的源目录；平台 Wiki 的 Markdown 源文件仍在
`wiki/`。后续新增知识库不再放入日期版本目录或其他 `docs/` 子目录。

实现、导入、权限过滤、向量/关键词召回以及 PDF/图片混合索引的完整说明以
[`ARCHITECTURE_DESIGN/CygnusX_knowledge_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_knowledge_architecture.md)
为准；面向用户和管理员的说明见
[`wiki/features/knowledge-base.md`](../../wiki/features/knowledge-base.md)，本文档保留目录约定与操作入口。
[`knowledge-base-implementation.md`](knowledge-base-implementation.md) 是较早的实现说明，细节以架构文档为准。

运行时采用“一份数据、两个消费方”：实验室知识库页面的导航读取数据库中所属知识库可见的文档
（待审/已拒绝版本带状态标记），AI `knowledge_search` 只读取已发布且允许检索的文档。两者共享
`knowledge_bases`、`kb_documents` 和版本表，但分别受 `show_in_lab`、`ai_searchable` 与
`is_enabled` 控制。

## 目录约定

- 单篇、无附件的知识文档可以直接保存为 `docs/knowledge/<document>.md`。
- 包含多篇文档、PDF、图片或其他附件的领域知识库使用
  `docs/knowledge/<knowledge-base-id>/` 独立目录。
- 领域知识库的入口 Markdown、附件和该知识库专属资源应保存在同一个领域目录内。
- `docs/knowledge/` 下的入口文档要进入数据库（进而出现在实验室知识库导航或 AI 检索），需在
  `docs/knowledge/meta.yaml` 登记并运行同步/导入脚本；`wiki/**/*.md` 由 `meta.yaml` 的
  `collections` 自动发现。实验室导航以数据库为准，不直接读取 `meta.yaml`。
- 需要进入数据库索引的知识库，应由对应导入或同步脚本从 `docs/knowledge/` 读取，不应引用
  日期版本目录。

## 当前领域知识库

| 知识库 | 入口文件 | 导入方式 |
| --- | --- | --- |
| RNA-seq | `docs/knowledge/rna-seq/RNA-seq.md` | `scripts/import_rnaseq_knowledge.py` |
| ATAC-seq | `docs/knowledge/atac-seq/ATAC-seq.md` | `scripts/import_atacseq_knowledge.py` |
| 单细胞 RNA-seq | `docs/knowledge/sc-seq/sc-seq.md` | `scripts/import_scseq_knowledge.py` |
| 测序与生信质量控制 | `docs/knowledge/qc/README.md` | `scripts/import_qc_knowledge.py` |
| 云计算与平台运维 | `docs/knowledge/cloud/README.md` | `scripts/import_cloud_knowledge.py` |

管理后台的知识库资源和文档归属以数据库为准，不应把目录文件数量当作页面展示数量。内置的 `qc`
与 `cloud` 资源会由 `KnowledgeBaseService` 幂等补齐；正文需执行对应导入脚本后才会进入文档、分块
和检索索引。页面导航只展示所属知识库同时满足 `show_in_lab=true` 与 `is_enabled=true` 的文档
（待审/已拒绝版本在目录中带状态标记）。AI 检索只使用已发布、所属知识库 `ai_searchable=true`
且 `is_enabled=true` 的内容（历史 `kb_id` 为空的文档按兼容规则处理），并按文档/知识库的项目范围过滤。

## 平台帮助知识

面向普通用户的平台功能说明应维护在 `docs/knowledge/platform/`，并在
`meta.yaml` 中登记后由 `scripts/sync_knowledge_from_files.py` 同步。当前入口为：

| 文档 | 说明 |
| --- | --- |
| `platform/ai-assistants-and-overdrive.md` | AI 助手职责、超频模式（Overdrive）、协作边界与常见问题 |
| `platform/treasure-mouse.md` | 寻宝鼠页面定位、数据发现与编号溯源、预案流程与执行边界 |

不要将 `data/ai/README.md`、`data/ai/update_agent.md`、Agent YAML、系统提示词或架构草稿
直接作为用户知识库正文导入。这些文件是开发和运行配置，可能包含内部实现、过期说明或不适合向
普通用户展示的操作细节。平台能力、Agent 职责或入口发生变化时，应从这些源文件核对后，更新
对应的用户帮助文档，再执行同步。

`wiki/` 是用户、管理员和开发者共用的平台说明，已作为 `meta.yaml` 的 `collections` 集合自动
同步：脚本会索引其中所有 Markdown 页面，并跳过只提供侧边栏导航的 `wiki/_Sidebar.md`。更新 Wiki
后无需复制 Markdown；重新运行同步脚本即可写入新的文档版本、发布并更新分块与检索索引。

本地同步示例：

```bash
uv run python scripts/sync_knowledge_from_files.py \
  --meta-yaml docs/knowledge/meta.yaml \
  --auto-admin
```

## 新增知识库示例

```text
docs/knowledge/example-kb/
├── README.md
├── example-kb.md
├── file/
└── image/
```

新增后应同步检查：

1. `meta.yaml` 中的 `id` 唯一且 `file` 使用相对 `docs/knowledge/` 的路径；
2. Markdown 内附件路径在领域目录内可解析；
3. 导入脚本、测试、Agent Prompt 和 README 不再引用旧目录；
4. `/docs-static/knowledge/...` 静态资源路径和 AI 检索结果可正常访问。

检索由 `VectorRetrievalService` 执行权限感知的 pgvector 向量召回。embedding 模型缺失、向量生成
失败、维度不符、SQL 向量查询失败或没有向量命中时，回退关键词候选；向量候选存在时，关键词匹配
只用于对候选加权重排，不会额外并入第二套候选集（不是双路并集/RRF）。返回结果包含
`citation_id`、摘录、章节路径和文档链接，使用检索结果回答时应保留引用并回到原文核对关键结论。

Web 启动后，`KNOWLEDGE_AUTO_REINDEX_ENABLED=true`（默认）会异步增量对齐已发布文档的分块与
向量索引；只重建既有文档索引可运行 `make knowledge-reindex`。常规同步可用
`make sync-knowledge`，它会执行通用同步并串行运行 QC、Cloud 专用导入脚本；RNA-seq、ATAC-seq
和单细胞知识库仍需运行各自的导入脚本。

QC 目录包含多篇 Markdown 和大量附件，应使用专用导入脚本：

```bash
uv run python scripts/import_qc_knowledge.py --validate-sources
uv run python scripts/import_qc_knowledge.py --auto-admin --dry-run
uv run python scripts/import_qc_knowledge.py --auto-admin
```

导入时 PDF 使用文本提取，图片使用文件说明与可用时的 OCR 文本建立检索块；图片中的精确数值仍应
回到原图复核。
