# CygnusX 知识库（Knowledge Base）实现架构

> **用途**：记录现阶段知识库模块的完整实现方式——数据模型、内容导入、页面展示、编辑审核流、AI 助手检索集成与 AI 配置中心管理入口。
>
> **最后核对**：2026-10-22
>
> **状态说明**：知识检索使用现有 PostgreSQL/pgvector，Qwen 真实正文入库与语义召回已在隔离验收库通过三篇小样本验证；正式知识库尚未批量向量化，当前 Web 自动索引开关关闭。代码、运行配置、全库状态与小样本证据分别记录，部署和验收快照见 §9，检索边界见 §6.4。

> **适用范围**：实验室知识库页面、单细胞知识库、AI 助手 `knowledge_search` 工具、AI 配置中心「知识库」管理卡片。

## 这个知识库模块如何发挥作用

知识库模块把 Markdown、SOP、实验经验和专题教程变成可审核、可版本化、可检索的共享证据。导入脚本或页面编辑写入 `kb_documents` 与 `doc_revisions`，以 `current_rev`/`pending_rev` 区分当前版本和待审版本；只有当前已发布版本进入 `KnowledgeIndexService`，按 Markdown 标题切块写入 `kb_chunks`。配置可用时生成 1024 维 embedding；缺配置或生成失败仍保留 chunk 正文供关键词检索。

两个消费方按不同开关读取同一数据：实验室页面只展示 `show_in_lab=true` 且启用的知识库；AI `knowledge_search` 只检索已发布、可检索且启用的内容，并施加文档/知识库项目范围过滤。`VectorRetrievalService` 优先做有界 pgvector 召回；embedding 不可用或没有向量命中时回退关键词候选。关键词特征用于候选加权排序，不代表始终合并两套候选。工具返回 `citation_id`、文档链接、章节和摘录；Chat 提示词要求模型标注引用，前端把有效引用渲染为可打开的来源。

编辑、审核、问题反馈、导入和索引更新都留下版本与审计记录。静态图片、PDF 和数据附件按资产策略保留；可索引附件文本可成为文档衍生 chunk，原始附件不会因此成为个人记忆。知识库是经维护的证据层；用户偏好、项目经历和会话进展由独立的长期记忆系统承载，二者不会自动互相写入，详见[记忆架构](CygnusX_memory_architecture.md#知识库与长期记忆的边界)。

### 运行架构图：知识资产到页面与 AI 的双消费链路

```mermaid
flowchart TB
    Source[docs/knowledge Markdown\n页面编辑 · 批量导入] --> Doc[knowledge_bases + kb_documents\n库归属 · 可见开关]
    Doc --> Rev[doc_revisions\ncurrent_rev / pending_rev]
    Rev --> Review{审核状态}
    Review -->|发布| Index[KnowledgeIndexService\n切块 · embedding · 索引]
    Index --> DocEmbedding[LiteLLMProvider\n文档 embedding · 当前 Qwen/1024 维]
    DocEmbedding --> Chunks[(kb_chunks: section + content + model-tagged vector)]
    Review --> Audit[doc_audit_logs · editors · issues]
    Doc --> Lab[实验室知识库页面\nshow_in_lab + is_enabled]
    Chunks --> Search[VectorRetrievalService\npublished + KB/document project scope]
    Search --> QueryEmbedding[LiteLLMProvider\n同模型查询 embedding]
    QueryEmbedding --> Search
    Search --> Tool[knowledge_search function tool]
    Tool --> Agent[Chat / Studio / Worker Agent]
    Lab --> Reader[DocTree · Reader · Editor]
    Assets[图片/PDF/数据] --> Static[/docs-static 静态挂载]
    Reader --> Static
```

### 实现图：导入、审核、索引和检索调用关系

```mermaid
sequenceDiagram
    participant Import as import_scseq_knowledge.py / DocEditor
    participant API as api/v1/docs.py
    participant Docs as DocsService
    participant DB as knowledge DB tables
    participant Index as KnowledgeIndexService
    participant Search as VectorRetrievalService
    participant Tool as knowledge_search
    participant Agent as Chat Runtime

    Import->>Docs: upsert document + revision (idempotent)
    API->>Docs: edit document
    Docs->>DB: write pending_rev + audit/editor record
    API->>Docs: admin approve
    Docs->>DB: promote pending_rev to current_rev
    Docs->>Index: index published revision
    Index->>DB: chunks + embeddings + citation metadata
    Agent->>Tool: knowledge_search(query, limit)
    Tool->>Search: permission-filtered vector-first retrieval
    Search->>DB: permission-filtered vector recall; keyword fallback/rerank
    DB-->>Search: ranked citations and excerpts
    Search-->>Tool: citation_id + URL + excerpt
    Tool-->>Agent: evidence payload for answer
```

---

## 1. 概述

知识库模块承载两类内容：

- **实验室知识库**：面向用户的公共文档 / SOP / 实验经验，在「实验室知识库」页面展示，支持协同编辑与审核流；
- **单细胞知识库**等专题库：由批量导入脚本维护的教程语料；是否在实验室知识库页面展示由 `show_in_lab` 控制，AI 检索由单独开关控制。文档数量以当前数据库为准。

核心设计：**一份数据，两个消费方**——页面展示与 AI 检索共用同一套表，通过 `knowledge_bases` 上的开关控制各自的可见范围。

---

## 2. 总体架构

```text
内容来源
  ├─ docs/knowledge/meta.yaml          知识库页面标题等展示配置
  ├─ scripts/import_scseq_knowledge.py 单细胞笔记批量导入（docs/knowledge/sc-seq/**.md）
  └─ 用户在「实验室知识库」页在线编辑（走审核流）
        │
        ▼
PostgreSQL
  ├─ knowledge_bases    知识库资源（lab / scseq / ...，含三个开关）
  ├─ kb_documents       文档主表（KB/项目归属、发布状态）
  ├─ doc_revisions      修订版本（正文存这里，current_rev / pending_rev 双指针）
  ├─ kb_chunks          发布正文衍生的章节块与 1024 维向量
  ├─ doc_editors        编辑者统计
  ├─ doc_audit_logs     审核日志
  └─ kb_issues          文档问题反馈
        │
        ├── 消费方 A：实验室知识库页面（只读 show_in_lab=true 的库）
        │     GET /docs/knowledge → KnowledgeView.vue（DocTree / DocReader / DocEditor）
        │
        ├── 消费方 B：AI 助手检索（已发布 + ai_searchable=true + is_enabled=true）
        │     knowledge_search function tool → VectorRetrievalService → 引用证据
        │
        └── 管理方：AI 配置中心 · 资源中心 · 知识库 Tab
              /admin/knowledge-bases → KnowledgeResourceTab.vue（开关 / 新建 / 删除 / 文档清单）

静态附件通过 /docs-static 提供；索引时 KnowledgeAssetService 可将可读附件内容补入派生 chunk，原始附件与版本化 Markdown 正文仍按各自存储路径管理。
```

### 2.1 原始资料、修订正文与向量的存储边界

| 载体 | 位置与用途 |
| --- | --- |
| 原始知识文件 | 仓库相对目录 `docs/knowledge/`；本机为 `/home/zj/zj_code_libarary/OmicHub/docs/knowledge`，保存 Markdown、PDF、图片、代码、数据与压缩归档 |
| 发布正文 | `omichub` 数据库的 `kb_documents` + `doc_revisions`；以已发布的 `current_rev` 为索引输入，不因磁盘文件存在而自动进入检索 |
| 知识向量 | 同一数据库 `kb_chunks.embedding vector(1024)`；章节、正文、模型标签与引用元数据同表保存 |
| 用户记忆向量 | `memory_facts.embedding`，另有 legacy `agent_memories.embedding`；与知识库共用 PostgreSQL 和 embedding Provider，不共用业务表或权限语义 |
| PostgreSQL 物理持久化 | 当前 `cygnusx-db` 使用宿主机 bind mount；实际目录与容器映射以[数据库架构 §4.4.1](CygnusX_database_architecture.md#441-当前部署的向量持久化位置)为准 |

Qwen 是生成向量的模型，pgvector 是保存和检索向量的数据库扩展；当前没有迁移到新的向量引擎。`docs/knowledge/` 不是 PostgreSQL 数据目录，向量也不以独立文件写回原文目录。数据库与原始资料需要分别纳入备份；保留数据库目录不等于已备份全部附件。

---

## 3. 数据模型

### 3.1 knowledge_bases（知识库资源表）

`src/cygnusx/infrastructure/database/models/knowledge_base.py`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String(64) PK | 机器标识（code），如 `lab`、`scseq` |
| `project_id` | String(64) nullable | 可选项目归属；NULL 表示平台级知识库 |
| `name` | String(128) | 显示名 |
| `description` | Text | 描述 |
| `show_in_lab` | Boolean | 是否在「实验室知识库」页面展示该库文档 |
| `ai_searchable` | Boolean | 是否允许 AI（`knowledge_search`）检索该库 |
| `is_enabled` | Boolean | 整体停用（页面与检索同时失效） |

迁移 `alembic/versions/o3p4q5r6s7t8_add_knowledge_bases.py` 建立知识库资源表并回填存量文档；具体条数以运行时数据库为准，不在架构基线固定快照计数。

- `lab`：实验室知识库，页面可展示且可供 AI 检索。
- `scseq`：单细胞专题知识库，可供 AI 检索；页面可见性由 `show_in_lab` 控制。

### 3.2 kb_documents（文档主表）

`src/cygnusx/infrastructure/database/models/knowledge_document.py`

| 字段 | 说明 |
|---|---|
| `doc_id` | 业务唯一标识（导入文档为 `scseq-<md5前12位>`，哈希自相对路径，幂等） |
| `title` / `category` / `file_path` | 标题 / 分类（聚合成分组树）/ 源文件路径 |
| `status` | 1=已发布 2=待审核 3=已拒绝 |
| `current_rev` / `pending_rev` | 当前生效版本 / 待审核版本（FK → doc_revisions） |
| `kb_id` | **归属知识库**（FK → knowledge_bases.id，NULL 按 lab 语义向后兼容） |
| `project_id` | 可选项目边界；NULL 表示平台级文档 |

### 3.3 doc_revisions（修订表）

`knowledge_revision.py`：`document_id` FK + `content`（**正文 Markdown 存这里**）+ `edit_summary` + `edited_by` + `status`。文档不直接存正文，所有内容版本化，支撑历史回溯与审核流。

### 3.4 辅助表

- `doc_editors`（`knowledge_editor.py`）：每文档编辑者及编辑次数；
- `doc_audit_logs`（`knowledge_audit_log.py`）：审核操作留痕；
- `kb_issues`（`knowledge_issue.py`）：读者对文档提交的问题反馈。

### 3.5 kb_chunks（检索索引表）

`src/cygnusx/infrastructure/database/models/knowledge_chunk.py` 定义文档分块索引：`document_id` + `chunk_index` 保证每篇文档内 chunk 顺序唯一；`section_path` 保留 Markdown 标题，`content` 存检索文本，`content_hash` 用于增量索引比较。迁移 `p4q5r6s7t8u9` 建表，`j4k5l6m7n8o9` 为知识库/文档增加 `project_id`，并为 `kb_chunks` 增加 `embedding vector(1024)`、`embedding_model` 与 HNSW cosine 索引。chunk 是当前发布版本的派生检索数据，不取代 `doc_revisions` 正文。

---

## 4. 内容来源与导入

### 4.1 单细胞笔记批量导入

`scripts/import_scseq_knowledge.py`，流程：

1. 遍历 `docs/knowledge/sc-seq/**/*.md`；
2. `doc_id = "scseq-" + md5(相对路径)[:12]`——稳定哈希，**幂等**，重复执行跳过已存在文档；
3. 标题取首个 H1，分类取顶层目录名（根目录文件归「单细胞总览」）；
4. **链接重写**：正文中相对图片/附件链接（`image/xxx.png` 等）正则匹配后解析为绝对路径，存在则重写为 `/docs-static/<相对docs/路径>`（逐段 URL 编码），不存在则保留原样并计数；
5. 写入 `kb_documents`（status=1 直接发布，`kb_id='scseq'`）+ `doc_revisions` + `doc_editors`；
6. `scseq` 知识库行不存在时兜底自建（防库被误删后导入失败）。

**原始 Markdown 与附件文件不动**，重写后的正文写入 DB 修订；附件实体经 `/docs-static` 提供。支持的 PDF/DOCX/PPTX/图片可在索引时提取文本进入衍生 chunk，R 脚本、Notebook、原始矩阵和压缩包没有统一的正文解析入口，不能把磁盘总字节直接视为可向量化文本量。

### 4.2 页面展示配置

`docs_service.list_knowledge` 从数据库读取属于 `show_in_lab=true` 且 `is_enabled=true` 知识库的文档；`docs/knowledge/meta.yaml` 用于页面展示配置，也由 `scripts/sync_knowledge_from_files.py` 读取显式条目及 `collections`（当前包含 `wiki/` 集合）。配置文件本身不构成 AI 检索索引；文件经导入/发布后，已发布文档的 `kb_chunks` 才是 AI 检索数据源。因此数据库文档数与 `docs/knowledge/**/*.md` 文件数不是同一统计口径。

### 4.3 发布索引与增量对齐

`DocsService` 在文档初次发布和审核通过时，将新 `current_rev` 正文交给 `KnowledgeIndexService.index_document()`，同一数据库事务中删除该文档旧 chunks、按 Markdown 标题切分并写新 chunks；数据库写入失败随发布事务回滚。每个 section 按最多 1800 字符切片，无 chunk overlap；chunk 内容哈希与 embedding 模型标签用于对账。

`src/cygnusx/main.py` 的 `_auto_reindex_knowledge()` 在 `KNOWLEDGE_AUTO_REINDEX_ENABLED=true` 时，于 Web 启动后通过 `asyncio.create_task()` 执行一次已发布版本的增量对齐。多实例用 PostgreSQL advisory lock 避免重复重建；`ensure_document_indexed()` 比较 chunk 顺序、内容哈希和模型标签，只重建变化文档。任务异常记录警告，不阻塞 Web 启动。

| 开关/操作 | 当前行为 |
| --- | --- |
| Settings 默认值 | `knowledge_auto_reindex_enabled=true`（`core/config.py`） |
| 2026-10-22 当前 Web 环境 | `KNOWLEDGE_AUTO_REINDEX_ENABLED=false`，启动时跳过自动索引 |
| 仅 restart 当前容器 | 沿用容器已有环境，不会因宿主机 `.env` 修改自动切换开关 |
| 修改 `.env` 后 force-recreate Web | 新环境进入容器；若开关为 true，启动后触发一次对齐 |
| Web 停止/重建 | 进程内任务被中断；没有独立队列任务、持久进度或断点续跑检查点 |

这是 Web 进程内的一次性后台协程，不是 Celery/Beat 定时任务。当前启动任务在整轮对齐后统一 `commit`；中断会使本事务尚未提交的变更回滚，已产生的模型调用费用不能回滚，下一次启动会重新对账。

embedding 未配置或生成失败时仍保存无向量 chunk。已配置模型但生成失败时，模型标签仍可能非空；增量比较不检查 `embedding IS NULL`，因此可能将失败块视为已对齐。后续检索虽可回退关键词，但不能据模型标签判断向量已就绪。

### 4.4 手动同步与重建入口

- `scripts/sync_knowledge_from_files.py`：同步 meta 声明的文件/集合，内容变化后创建修订；源文件缺失时跳过，没有自动删除对账。
- `scripts/import_scseq_knowledge.py`：路径哈希决定 doc_id；已有文档直接跳过，不能用重复导入代替内容/索引更新。
- `scripts/import_{atacseq,rnaseq,qc,cloud}_knowledge.py`：对应专题的专用导入路径，行为以各脚本为准。
- `scripts/reindex_knowledge_vectors.py` / `make knowledge-reindex`：重建已发布正文及附件 chunk；`--limit` 按文档计数，默认 10000，不能据此限定 embedding 调用数。当前脚本使用应用会话工厂，无专用维护 DSN、dry-run、持久进度和模型调用预算保护。

这些入口是现有运维工具，不表示全库入库已执行。本轮隔离小样本的 12 次 HTTP 尝试上限只存在于验收脚本，不是业务重建脚本已有能力。

---

## 5. 实验室知识库页面

- 前端：`frontend/src/views/KnowledgeView.vue` + `components/knowledge/`（DocTree 分类树 / DocReader / DocEditor / DocCreateModal / AuditPendingPanel / DocIssues / DocEditors），路由 `knowledge` / `knowledge-doc`；
- 后端：`src/cygnusx/api/v1/docs.py`（`/docs/knowledge*` 路由组）+ `application/services/docs_service.py`；
- **范围过滤**：导航列表按所属知识库的 `show_in_lab=true AND is_enabled=true` 过滤；文档详情也校验知识库可见状态。项目级隔离是 AI 检索链路的过滤条件，不应与页面列表权限混为一谈；
- 编辑走审核流：`PUT /docs/knowledge/{doc_id}` 写入 `pending_rev`，管理员在 `audit/pending` 审核通过后才切到 `current_rev`；`GET .../history|editors|issues` 提供历史、编辑者与问题反馈。

---

## 6. AI 助手集成（knowledge_search 工具）

**关键结论：知识库通过平台内置 function tool 提供检索增强，不走 MCP。文档按版本进入 `kb_chunks`，运行时优先 pgvector 召回，并保留关键词回退。**

### 6.1 工具挂载

普通聊天在模型支持 function calling 时将 `KNOWLEDGE_SEARCH_TOOL` 纳入本次请求工具表；Studio 工具 schema 也暴露同一功能。工具参数为 `query` 与 `limit`（1–8，默认 5）。工具是否实际调用由执行路径和模型工具选择决定。

### 6.2 系统提示引导

工具挂载后可追加 `KNOWLEDGE_SEARCH_SYSTEM_PROMPT_SUFFIX`：提示模型遇到平台知识、实验方法或生信流程问题先检索并基于结果回答，查不到时如实说明。是否调用及 query 仍取决于当前 Agent/运行时配置和模型工具选择。

### 6.3 分发与执行

- 分发：Chat Runtime、Studio 与部分子 Agent 的执行器将调用委托到 `studio_tools._knowledge_search`；普通 Chat 使用独立数据库 session 执行已提交知识索引的只读查询；
- 检索（`studio_tools._knowledge_search` → `VectorRetrievalService.search_knowledge`）：
  1. 数据库查询只取已发布文档及其 `kb_chunks`，并过滤 `knowledge_bases.ai_searchable/is_enabled`、兼容 `kb_id IS NULL` 的旧文档，以及文档和知识库的项目范围。项目会话可读平台级与当前项目内容，不读其他项目文档。
  2. 查询归一化后最多 1000 字符；使用 `AGENT_MEMORY_EMBEDDING_MODEL` 生成 1024 维查询向量，对 chunk 做 cosine/HNSW 候选检索，候选上限 `max(limit * 8, 40)`。缺模型、生成失败、维度不符、SQL 向量查询失败或没有向量命中时，改用关键词候选。
  3. 关键词候选最多 12 个词，匹配 chunk 正文和文档标题。向量候选存在时，关键词覆盖只用于对向量候选加权排序，并不额外并入关键词候选集。
  4. 结果摘录最多 600 字符，工具 limit 限制为 1–8、默认 5；结果含稳定 `citation_id`、`doc_id`、标题、类别、章节路径、摘录、URL 和排序分数。
- 结果作为 tool message 回填，LLM 基于摘录组织回答；`/knowledge/{doc_id}` 链接可跳转全文页。

Chat 可从多个运行时入口调用该工具，最终复用 `_knowledge_search`；普通 Chat 为知识读取使用独立数据库 session，避免与请求 session 并发使用。提示词要求模型在相应陈述后输出 `[[citation:<citation_id>]]`。前端只把当前消息来源集合中存在的引用标记渲染为来源按钮；无对应检索来源的标记不生成可点击引用。

### 6.4 已知局限

| 局限 | 影响 |
|---|---|
| 不是双路并集/RRF | 向量候选存在时，关键词只重排向量候选；关键实体对应的其他 chunk 可能未进入候选 |
| 600 字符摘录 | 模型只看到局部片段，复杂章节上下文可能不足 |
| 单 query | 不自动拆分/扩展多条查询，召回受模型给出的 query 质量影响 |
| 共享模型且知识 SQL 未过滤模型标签 | 知识 chunk 与个人记忆使用独立表和索引，但共用 embedding 模型/Provider/维度；知识向量查询仅排除空向量，未限定 `embedding_model`，换模型需同步处理旧向量，不能混用同维度的不同向量空间 |
| 无显式知识相似度门槛 | 当前直接按 cosine 候选排序，未设置知识检索的 `min_similarity` |
| 工具结果预算不统一 | LangGraph 普通工具 JSON 按 4000 字符截断；8 条 600 字符摘录加元数据可能被截断，其他运行时处理不完全相同 |
| 私有知识访问边界未闭环 | AI 检索有项目过滤，但无用户级知识 ACL；页面按 KB 展示开关读取，整个 `docs/` 的静态挂载由认证 `/docs` 前缀放行，不能将这些机制解释为私有附件权限 |

**当前能力边界**：pgvector 分块索引、关键词回退、关键词候选重排和可追溯引用已接入；隔离库真实 Qwen 正文写入与向量召回已验证。全库向量覆盖、双路 RRF、质量基线、生产规模 EXPLAIN/P95 和可靠后台入库仍未验收。

### 6.5 与个人记忆共处的上下文契约

`AgentMemoryService.build_prompt_context_v2()` 在工具调用前将用户记忆追加到系统提示词，并使用 `<user_memory>` 明示其可能不可信、过时、不能作为指令。代码默认总预算 6000 字节，blocks/episode 配额分别为 2800/3200 字节；实际分配先预留 episode，再装配 blocks 和剩余事实。

知识库结果由 `studio_tools._knowledge_search()` 返回普通 JSON，随后作为 `role=tool` 消息进入模型上下文。两者处于同一轮消息序列，但没有统一来源排序、跨来源字节预算或知识专用的等价不可信包装。L4 Manager 直接读取个人记忆；子 Agent/研究计划可调用知识工具，尚不是统一的记忆与知识检索网关。记忆侧完整契约见[记忆架构](CygnusX_memory_architecture.md)。

---

## 7. AI 配置中心管理入口

「AI 配置中心 → 资源中心 → 知识库」Tab，与 MCP / 技能 / 助手 / 联网搜索同级。

- 后端：`api/v1/admin/knowledge_bases.py` + `application/services/knowledge_base_service.py` + `schemas/knowledge_base.py`，路由 `/admin/knowledge-bases`（`router.py`，AdminRequired）：

  | 方法 | 路径 | 说明 |
  |---|---|---|
  | GET | `/admin/knowledge-bases` | 库列表（含 doc_count 聚合） |
  | POST | `/admin/knowledge-bases` | 新建（id 限小写字母/数字/连字符） |
  | PUT | `/admin/knowledge-bases/{kb_id}` | 更新名称/描述/三个开关 |
  | DELETE | `/admin/knowledge-bases/{kb_id}` | 删除（库内仍有文档时拒绝） |
  | GET | `/admin/knowledge-bases/{kb_id}/docs` | 库内文档清单（≤500） |

- 前端：`components/admin/KnowledgeResourceTab.vue`（左列库列表 + 右侧配置面板 + 文档抽屉），API 封装 `api/admin/knowledgeBase.ts`，注册于 `views/AdminAIResourceCenterView.vue`。

### 开关语义速查

| 开关 | 关闭效果 |
|---|---|
| show_in_lab | 该库文档从「实验室知识库」页面消失（AI 检索不受影响） |
| ai_searchable | AI 助手检索不到该库（页面展示不受影响） |
| is_enabled | 页面与检索同时失效（总开关） |

---

## 8. 关键文件清单

| 层 | 文件 |
|---|---|
| 模型 | `infrastructure/database/models/knowledge_base.py`、`knowledge_document.py`、`knowledge_revision.py`、`knowledge_chunk.py`、`knowledge_editor.py`、`knowledge_audit_log.py`、`knowledge_issue.py` |
| 迁移 | `alembic/versions/o3p4q5r6s7t8_add_knowledge_bases.py`、`p4q5r6s7t8u9_add_kb_chunks.py`、`j4k5l6m7n8o9_add_pgvector_project_boundaries.py` |
| 用户侧 API | `api/v1/docs.py` + `application/services/docs_service.py` |
| 管理侧 API | `api/v1/admin/knowledge_bases.py` + `application/services/knowledge_base_service.py` + `application/schemas/knowledge_base.py` |
| 索引与附件 | `application/services/knowledge_index_service.py`、`knowledge_asset_service.py`、`knowledge_bootstrap_service.py` |
| AI 检索 | `application/services/vector_retrieval_service.py`、`studio_tools.py`（`_knowledge_search`）、`chat/runtime_support.py`（`_knowledge_search_chat`） |
| 导入与重建脚本 | `scripts/sync_knowledge_from_files.py`、`import_scseq_knowledge.py`、`import_qc_knowledge.py` 等分库导入脚本、`reindex_knowledge_vectors.py` |
| 前端 | `views/KnowledgeView.vue` + `components/knowledge/*`（用户侧）；`components/admin/KnowledgeResourceTab.vue` + `api/admin/knowledgeBase.ts` + `views/AdminAIResourceCenterView.vue`（管理侧） |
| 启动对齐与静态附件 | `main.py`（`_auto_reindex_knowledge`；`docs/` → `/docs-static` 挂载） |

---

## 9. 当前部署与 Qwen 小样本验证（2026-10-22）

本节是本次调查/测试的时点快照，不是运行时常量或全量准入声明。当前模型为 `Qwen/Qwen3-Embedding-8B`，通过独立 OpenAI-compatible Provider 生成 1024 维向量；存储仍使用现有 PostgreSQL/pgvector。

### 9.1 源语料与正式库状态

本地 `docs/knowledge/` 有 2029 个常规文件、604 个子目录、24,889,068,946 字节（约 23.18 GiB），包含 308 篇 Markdown、386 个 PDF；根目录 `sc-seq.zip` 占总字节约 66.46%。统计未展开压缩包。正文、附件、代码、原始数据与压缩归档混合存放，不能把全部 23.18 GiB 当作待向量化正文。

正式库 `omichub` 的只读快照与小样本前后复核均为：6 个知识库、367 篇文档、475 个修订、2778 个 chunk；仅 158 篇文档有 chunk，现有 chunk 的向量与模型标签全部为空。

| 知识库 | 文档 | chunk | 有向量 chunk |
| --- | ---: | ---: | ---: |
| lab | 71 | 673 | 0 |
| scseq | 209 | 0 | 0 |
| qc | 63 | 1513 | 0 |
| cloud | 23 | 562 | 0 |
| atacseq | 1 | 30 | 0 |
| 其余 1 个知识库 | 0 | 0 | 0 |
| 合计 | 367 | 2778 | 0 |

数据库外键层面的孤立 chunk 为 0；Web 环境中 4 篇文档的登记源路径不可访问，对应 97 个 chunk，尚不能据此判定文件已删除。个人记忆已完成的向量回填不改变本表，也不能用于证明知识库全量向量化已完成。

### 9.2 三篇正文的真实入库与召回

测试使用正式库中已发布的三个修订正文，只读读取源库，在独立 Stage 0 PostgreSQL 的 `cygnusx_maint` 中创建临时 schema。未解析附件，未写正式库，未修改生产开关。

| 文档 | 已提交向量块 | 查询 Top 1 | Top 1 cosine |
| --- | ---: | --- | ---: |
| FAST5 | 3 | 对应文档 | 0.737385 |
| TOML | 1 | 对应文档 | 0.746265 |
| bwtool | 2 | 对应文档 | 0.806552 |

6 个块经提交后在新会话核验，均为 1024 维且模型标签正确。3 次查询均执行真实向量 SQL，关键词回退次数为 0；重复增量索引跳过三篇且额外模型调用为 0。真实 embedding HTTP 请求共 9 次（全部 200），返回 usage 合计 653 tokens；金额未查询，不记作 0。测试临时 schema 已删除，源库前后聚合计数保持。

正式实例为 PostgreSQL 14 / pgvector 0.8.6；此次隔离实例为 PostgreSQL 15 / pgvector 0.8.7。该结果证明小样本正文可生成向量、提交入库并召回，不证明全库语义质量、附件覆盖、生产规模性能或后台任务可靠性。

证据：[计划](../evidence/knowledge-qwen-pilot-20261022/plan.json)、[结果](../evidence/knowledge-qwen-pilot-20261022/result.json)、[审计](../evidence/knowledge-qwen-pilot-20261022/audit.json)、[调用台账](../evidence/knowledge-qwen-pilot-20261022/call-ledger.json)。验收脚本不属于生产启动或定时任务，容器重启不会自动重跑这次测试。
