# 记忆与知识库

CygnusX 的上下文能力分两条线：**记忆**保存用户/项目在长期交互中形成的偏好、事实与工作状态；**知识库**保存实验室可复用的文档与方法。两者都使用 PostgreSQL + pgvector 检索，但数据模型、写入路径和消费方式不同。

> **当前状态**：自研记忆系统与知识库均已落地；记忆 v2 默认关闭（灰度），知识库向量检索为当前实现。引擎层**没有 mem0**：遗留 `mem0_memories` 表与 `MEM0_*` 配置是受保护的迁移残留，禁止顺手清理。

## 记忆系统

### 数据模型

| 表 | 作用 | 关键字段 |
| --- | --- | --- |
| `agent_memories` | 旧版归档记忆 | 兼容保留 |
| `memory_blocks` | 常驻块（profile / preferences / current_focus） | 乐观锁 `version` |
| `memory_facts` | 可检索事实 | `scope`、`embedding vector(1024)`、`content_hash`、`superseded_by` |

`memory_facts.scope` 支持 `profile` / `preference` / `project` / `summary`；共享分区使用 `agent_id=""`，profile 与 preference 可跨 Agent 共享。事实带 `content_hash` 幂等，修正通过 `superseded_by` 链保留历史，不物理覆盖。

索引：HNSW cosine；embedding 由 fastembed 生成，不依赖外部向量服务。

### 注入与写入

```text
会话创建 / 每轮请求
  → build_prompt_context_v2
      常驻 memory_blocks + 检索 memory_facts
      时间衰减排序，取 top 5
      总预算约 3200 字节
      以 <user_memory> 不可信块包裹注入
  → 模型请求

异步结算
  → settle_session_memory(游标 + 区间幂等)
  → 抽取事实/偏好 → memory_facts / memory_blocks
  → AgentTeams 合成会话排除
```

- 记忆工具：`save`、`update_block`、`search`、`forget`。
- v2 开关：`memory_v2_enabled`，默认关闭；关闭时走旧归档行为。
- 观测指标：`memory.settle_skipped`、`memory.l4_inject_degraded` 等。

### 协作室注入纪律

- Manager：注入共享分区 + 当前 Agent 分区；
- 专家 Worker：**零记忆注入**，避免跨角色污染；
- 注入失败降级时记录指标，不阻断主任务。

## Studio 文件记忆

OmicStudio 使用文件型记忆，与 DB 记忆并行：

| 资产 | 规则 |
| --- | --- |
| `MEMORY.md` | 索引，最多 200 条 / 8000 字符 |
| `.memory/*.md` | 具体记忆文件，通过 `workspace_read` 读取 |
| Git 检查点 | 单文件 10 MB 上限，保留 20 个引用，恢复前先检查点 |

文件记忆随工作区归档/恢复；不要把 DB 记忆与文件记忆当成同一份数据。

## 知识库

### 一套文档，两个消费者

知识库文档同时服务**人在实验室页面阅读**和**AI 检索**。`knowledge_bases` 上有三个独立口径：

| 字段 | 作用 |
| --- | --- |
| `show_in_lab` | 是否在实验室知识库页面展示 |
| `ai_searchable` | 是否进入 AI 检索 |
| `is_enabled` | 集合级开关 |

### 数据模型

| 表 | 作用 |
| --- | --- |
| `knowledge_bases` | 知识库集合与消费口径 |
| `kb_documents` | 文档元数据、`current_rev` / `pending_rev` |
| `doc_revisions` | 版本化正文 |
| `doc_editors` | 编辑者与权限 |
| `doc_audit_logs` | 审阅与修改审计 |
| `kb_issues` | 文档问题跟踪 |

### 写入与检索

```text
Markdown 源（wiki/、docs/knowledge/）
  → make sync-knowledge
  → 文档版本 + 分块 + embedding
  → knowledge_bases / kb_documents / doc_revisions
  → AI knowledge_search（pgvector）

人工页面
  → 编辑 / 提交审阅 / 发布新 revision
  → 审计记录
```

- `docs/knowledge/meta.yaml` 把 `wiki/**/*.md` 定义为自动集合，排除 `_Sidebar.md`；改完 Wiki 需运行 `make sync-knowledge`，只重建既有向量用 `make knowledge-reindex`。
- 检索以 pgvector 语义检索为当前实现；旧文档中“子串匹配”的结论已被取代。
- 知识库内容属于“实验室知识”，不是平台架构的权威来源；平台边界仍以代码和 `ARCHITECTURE_DESIGN/` 为准。

## 与计费、审计的边界

- 记忆/知识注入本身不产生 token 账单；账单只来自 Provider 实际 `usage`，见[模型路由与 Token 计费](model-routing-billing)。
- 记忆写入、技能调用与知识检索分别有审计/指标，不要依赖应用日志推断完整历史。

## 维护要点

1. 修改记忆模型或 scope 语义 → 先读记忆架构文档，检查 v2 开关与迁移。
2. 修改知识库同步规则 → 同时检查 `meta.yaml`、分块策略和 `knowledge_search` 的可见性过滤。
3. 不要读取或记录用户的完整记忆正文到日志；审计只保留必要元数据。
4. 不新增第二套向量库；平台统一使用 pgvector。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| 记忆服务 | `src/cygnusx/application/services/agent_memory_service.py` |
| FactStore / 向量 | `src/cygnusx/infrastructure/database/vector/` |
| 记忆工具 | 平台工具 Schema + 运行时执行 |
| 知识库服务 | 知识库应用服务与 `api/v1/knowledge*` |
| 同步脚本 | `docs/knowledge/meta.yaml` + `make sync-knowledge` |

## 关联文档

- 权威基线：[`CygnusX_memory_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_memory_architecture.md)、[`CygnusX_knowledge_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_knowledge_architecture.md)
- [Agent 运行时](agent-runtime) · [数据库基础设施](database) · [实验室知识库](../features/knowledge-base)
