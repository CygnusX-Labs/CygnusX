# 实验室知识库实现方式与架构汇总

> 本文是团队快速理解用的摘要，不是权威基线。实现细节以
> [`ARCHITECTURE_DESIGN/CygnusX_knowledge_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_knowledge_architecture.md)
> 为准；用户操作与同步说明见 [`wiki/features/knowledge-base.md`](../../wiki/features/knowledge-base.md)
> 和 [`docs/knowledge/README.md`](README.md)。最后核对：2026-10-21。

---

## 1. 功能定位

知识库把 Markdown、SOP、实验经验和专题教程变成可审核、可版本化、可检索的共享证据：

- **文档浏览**：左侧分类目录 + 右侧 Markdown 阅读器，支持目录大纲；
- **在线编辑与审核**：普通用户提交待审版本，管理员审核或直接发布；
- **AI 检索**：通过平台内置 function tool `knowledge_search` 检索已发布内容，返回可追溯引用；
- **静态资源**：图片、PDF 等附件通过 `/docs-static/` 提供；
- **管理入口**：AI 配置中心 → 资源中心 → 知识库。

知识库是经维护的证据层；用户偏好、项目经历和会话进展由独立的长期记忆系统承载，两者不会自动互相写入。

---

## 2. 总体架构

整体采用 **Markdown 源 + 数据库运行时副本** 的架构。仓库中的 Markdown 是待同步的源内容，PostgreSQL 中的文档版本、分块与索引才是页面和 AI 读取的运行时权威数据。

```text
Markdown 源（docs/knowledge/、wiki/）
  → 同步/导入脚本
  → PostgreSQL
      knowledge_bases / kb_documents / doc_revisions / kb_chunks
  → 消费方 A：实验室知识库页面（show_in_lab + is_enabled）
  → 消费方 B：AI knowledge_search（已发布 + ai_searchable + is_enabled + 项目范围）
  → 管理方：/admin/knowledge-bases
```

数据库是导航和检索的权威源。仓库 Markdown 修改后必须运行同步/导入脚本才会生效；数据库没有对应文档时，文档详情接口可回退读取 `meta.yaml` 中登记的本地文件。

---

## 3. 数据模型

| 表 | 作用 | 关键字段 |
| --- | --- | --- |
| `knowledge_bases` | 知识库集合与消费口径 | `show_in_lab`、`ai_searchable`、`is_enabled` |
| `kb_documents` | 文档元数据与发布状态 | `doc_id`、`kb_id`、`project_id`、`current_rev` / `pending_rev`、`status` |
| `doc_revisions` | 版本化正文 | `content`、`edit_summary`、`edited_by`、`status` |
| `kb_chunks` | 发布正文派生的检索块 | `section_path`、`content`、`content_hash`、`embedding vector(1024)`、`embedding_model` |
| `doc_editors` | 编辑者统计 | 文档、用户、编辑次数 |
| `doc_audit_logs` | 审核留痕 | 操作、审核人、原因 |
| `kb_issues` | 文档问题反馈 | 文档、提交人、状态 |

- `status`：`1=已发布`、`2=待审核`、`3=已拒绝`。
- `kb_id` 为空时按历史 lab 语义兼容；新文档应显式归属知识库。
- `project_id` 为空表示平台级文档；项目知识库不能泄露给无关项目。
- `kb_chunks` 是当前发布版本的派生索引，不取代 `doc_revisions` 中的正文。

---

## 4. 内容来源与同步

| 来源 | 用途 | 同步方式 |
| --- | --- | --- |
| `docs/knowledge/` | 领域知识库、SOP、平台帮助文档 | `docs/knowledge/meta.yaml` 的显式 `items` + 同步/导入脚本 |
| `wiki/` | 平台、部署、运维、开发和安全说明 | `meta.yaml` 的 `collections` 自动发现所有正文页面 |
| `wiki/_Sidebar.md` | Wiki 导航 | 不进入检索正文 |

`docs/knowledge/meta.yaml` 负责导入登记、页面标题和数据库未导入时的文件回退，**不是运行时导航或 AI 检索的路由表**。实验室导航由数据库查询决定。

常见同步入口：

```bash
# 通用文档 + Wiki 集合，并串行运行 QC、Cloud 专用导入
make sync-knowledge

# 只重建数据库中已发布文档的分块与向量
make knowledge-reindex
```

RNA-seq、ATAC-seq、单细胞知识库仍分别使用 `scripts/import_rnaseq_knowledge.py`、`scripts/import_atacseq_knowledge.py`、`scripts/import_scseq_knowledge.py`。所有导入脚本按稳定文档 ID 幂等写入，重复执行不会重复建文档。

文档初次发布、管理员直接发布或审核通过时，`DocsService` 会将新的 `current_rev` 交给 `KnowledgeIndexService.index_document()`，在同一事务中重建该文档的 chunks。普通用户编辑写入 `pending_rev`，不进入页面当前版本和检索索引。

---

## 5. 索引与检索

### 5.1 分块与向量

- 按 Markdown 标题切分 section，每个 section 最多 1800 字符，无 chunk overlap；
- 配置可用时为每个 chunk 生成 1024 维 embedding，并记录 `embedding_model`；
- `embedding` 使用 HNSW cosine 索引；
- embedding 缺失或 Provider 生成失败时仍保存无向量 chunk，后续可走关键词路径；
- 启动时 `KNOWLEDGE_AUTO_REINDEX_ENABLED=true`（默认）异步增量对齐已发布文档；多实例用 PostgreSQL advisory lock 避免重复重建。

### 5.2 AI 检索

`knowledge_search` 是平台内置 function tool，不走 MCP。参数为 `query` 与 `limit`（1–8，默认 5）。

```text
knowledge_search
  → VectorRetrievalService.search_knowledge
  → 权限过滤（已发布、项目范围、ai_searchable、is_enabled）
  → pgvector 向量召回
  → embedding 不可用/无向量命中时回退关键词候选
  → 关键词对候选加权重排
  → citation_id + 标题 + 章节 + 摘录 + /knowledge/{doc_id}
```

关键边界：

- **不是双路并集/RRF**：向量候选存在时，关键词只用于重排这些候选，不会额外并入关键词候选集；
- 查询向量使用 `AGENT_MEMORY_EMBEDDING_MODEL` 生成；
- 单条摘录最多 600 字符；
- 工具结果中的 `citation_id` 稳定，前端只把当前消息来源集合中存在的 citation 标记渲染为可点击来源。

---

## 6. 页面与管理端

用户侧：

- 前端 `frontend/src/views/KnowledgeView.vue` + `components/knowledge/`（DocTree / DocReader / DocEditor / DocCreateModal / AuditPendingPanel / DocIssues / DocEditors）；
- 路由 `knowledge` / `knowledge-doc`；
- 后端 `src/cygnusx/api/v1/docs.py` + `application/services/docs_service.py`；
- 导航只展示 `show_in_lab=true` 且 `is_enabled=true` 的知识库内文档，待审/已拒绝版本带状态标记。

管理侧：

- `api/v1/admin/knowledge_bases.py` + `application/services/knowledge_base_service.py`；
- 路由 `/admin/knowledge-bases`，支持库列表、新建、更新三个开关、删除和文档清单；
- `qc`、`cloud` 为内置资源，由服务幂等补齐；库内仍有文档时禁止删除。

开关语义：

| 开关 | 关闭效果 |
| --- | --- |
| `show_in_lab` | 该库文档从实验室知识库页面消失（AI 检索不受影响） |
| `ai_searchable` | AI 助手检索不到该库（页面展示不受影响） |
| `is_enabled` | 页面与检索同时失效（总开关） |

---

## 7. 静态附件与混合索引

- FastAPI 将仓库 `docs/` 挂载到 `/docs-static`；
- 导入时把 Markdown 中的相对附件路径重写为 `/docs-static/...`；
- `KnowledgeAssetService` 可将同级或正文引用的 PDF、图片内容补入文档衍生 chunk；
- PDF 使用文本提取；图片使用文件名、alt 文本、尺寸和可用时的 OCR 文本；
- 附件索引不是视觉 embedding，也不会理解没有文字、alt 或语义文件名的图片；
- 每篇文档最多处理 64 个附件，单附件最多写入 40,000 字符。

---

## 8. 关键边界与限制

- **Markdown 不会在运行时被自动扫描**：文件放在 `docs/knowledge/` 或 `wiki/` 后，必须同步/导入才可被页面和 AI 使用；
- **页面与 AI 口径不同**：页面看 `show_in_lab` / `is_enabled`，AI 还要看发布状态、`ai_searchable` 和项目范围；
- **检索不是双路 RRF**：关键词是向量召回的回退与重排信号，不是独立的第二路候选集；
- **共享 embedding 配置**：知识 chunk 与个人记忆使用独立表和索引，但共用 `AGENT_MEMORY_EMBEDDING_MODEL`；换模型须重建知识索引；
- **引用粒度**：当前是“知识库文档 + 附件块”，不是独立 PDF 页码引用或图片区域坐标引用；
- **运行验收**：代码已接入 pgvector、关键词回退/重排和引用，但真实 PostgreSQL/Provider 的查询计划、延迟和质量基线仍需验收。

---

## 9. 如何新增或更新一篇知识库文档

1. 将稳定、面向目标读者的 Markdown 放入 `docs/knowledge/`，或更新对应 Wiki 正文。
2. `docs/knowledge/` 的入口文档在 `meta.yaml` 添加唯一 `id`、标题、分类和相对路径；Wiki 页面由 `collections` 自动发现，不需要逐篇登记。
3. 检查文档中的相对链接、图片和附件路径。
4. 运行 `make sync-knowledge`（或对应领域导入脚本），必要时运行 `make knowledge-reindex`。
5. 用平台聊天的 `knowledge_search` 验证目标术语能被召回，并回到原文核对关键结论。

---

## 10. 关联文档

- 权威基线：[`CygnusX_knowledge_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_knowledge_architecture.md)
- 用户说明：[实验室知识库](../../wiki/features/knowledge-base.md)、[记忆与知识库](../../wiki/architecture/memory-knowledge.md)
- 目录约定：[`docs/knowledge/README.md`](README.md)
- 早期实现细节：[`knowledge-base-implementation.md`](knowledge-base-implementation.md)
