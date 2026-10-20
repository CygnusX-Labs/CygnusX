# 数据库基础设施

CygnusX 使用 PostgreSQL + pgvector 作为主数据存储，SQLAlchemy 2.0（asyncpg）访问，Alembic 管理 schema。**Alembic 是 schema 的唯一事实来源**：应用启动不执行 `create_all`，任何模型变更都必须有迁移。

> **当前状态**：116 张 ORM 表、迁移链、连接池分角色、仓储分层与漂移检查已实现。数据库结构以迁移和 `check_schema_drift.py` 对账为准，不以文档中的表数量为契约。

## 连接与会话

| 角色 | 引擎/池 | 说明 |
| --- | --- | --- |
| Web | `AsyncAdaptedQueuePool` | 连接复用，受池上限约束 |
| Worker / Beat | `NullPool` | 每任务独立连接，避免跨 fork 复用 |
| 后台一次性任务 | 非池化连接 | 短生命周期，显式关闭 |

- `session.py` 按进程角色分流；可选择只读副本，副本不可用时回退主库。
- 连接池指标接入 OpenTelemetry；容量与超时可观测。
- 不在 Web 进程持有跨请求长事务；长任务交给 Worker。

## ORM 契约

| 规则 | 说明 |
| --- | --- |
| 全量注册 | `models/__init__.py` 导入并导出所有模型；漏注册会导致元数据/迁移漂移 |
| 类型对齐 | JSONB、`UniqueConstraint`、索引名、HNSW 参数必须与迁移一致 |
| 向量类型 | 自实现 `vector.py` 的 `Vector` 类型，不依赖第三方 pgvector ORM 扩展 |
| 关系加载 | 默认 `lazy="selectin"`，避免异步上下文中的隐式懒加载 |
| 外部表 | 非 ORM 表（如遗留 `mem0_memories`）列入 `_NON_ORM_TABLES` 豁免对账 |

## 仓储分层

| 层级 | 适用 | 做法 |
| --- | --- | --- |
| 核心域 | 任务、Agent、知识库、计费等 | Protocol 接口 + 实现，领域层不依赖 ORM |
| 轻量域 | CRUD 为主、规则少 | 应用服务直接使用模型/会话，达到升格条件再抽象 |

当前约有 19 个领域仓储接口、24 个实现；具体清单以 `src/cygnusx/domain/` 与 `infrastructure/database/repositories/` 为准。新增仓储前先判断是否真的需要抽象，避免为一次性查询引入空壳接口。

## 迁移与对账

```bash
make check-migrations        # 迁移链静态校验（单 head、依赖完整）
make migrate-new m="..."     # 生成迁移
make migrate                 # 应用迁移
make migrate-merge           # 合并并行分支
make check-alembic-heads     # 多 head 检测
uv run python scripts/check_schema_drift.py   # ORM ↔ 实际库对账
```

- 多人并行改模型后必须检查 `alembic heads`；出现多 head 先合并再提交。
- 容器 entrypoint 在 `RUN_MIGRATIONS=1` 时执行迁移，并用 `check_schema_drift.py` fail-fast。
- 测试/真实环境的结构差异不能用“手工改库”掩盖；修正迁移或模型，再对账。

## 数据模型分区（概览）

| 域 | 代表表 |
| --- | --- |
| 身份与项目 | `users`、`projects`、`project_members`、`audit_logs` |
| 会话与消息 | `chat_sessions`、`chat_messages`、`chat_message_events` |
| Agent | `agent_templates`、`agent_memories`、`memory_blocks`、`memory_facts` |
| 任务与执行 | `tasks`、`task_*`、`agent_tool_invocations`、`research_plans` |
| Dataset/交付 | `datasets`、`dataset_versions`、`dataset_assets`、`dataset_samples`、`project_export_jobs` |
| 知识库 | `knowledge_bases`、`kb_documents`、`doc_revisions`、`doc_editors`、`kb_issues` |
| MCP/Skill | `mcp_servers`、`mcp_logs`、`mcp_builds`、`mcp_versions`、`skills`、`skill_versions`、`skill_invocations` |
| 参考数据 | 参考基因组使用 SQLite/FTS5 独立模块，不走 Alembic |

表数量会随迁移变化；本表只用于定位，权威定义在模型与迁移。

## 参考基因组模块

参考基因组不是普通业务表：它以**版本化 SQLite + FTS5** 独立存储 FASTA/CDS/UTR/GO Slim/启动子等索引，供 JBrowse、BLAST 和注释检索使用。

- 数据文件与版本由离线构建流程产生，运行时只读；
- 不用 Alembic 管这些数据文件，但需要记录当前版本与路径；
- 升级参考库时要验证坐标体系、注释版本和下游 Flow 的参考选择一致。

详见[参考基因组与数据库](../features/reference-database)与数据库架构文档 §11。

## 管理端

| 端点 | 作用 |
| --- | --- |
| `/admin/database/health` | 连接、池、复制与基本健康状态 |
| `/admin/database/drift` | ORM 与库结构差异 |

管理端只读展示，不提供在线改表能力。

## 修改门禁

1. 任何模型变更：生成迁移 + `make check-migrations` + `check_schema_drift.py`。
2. 新增外部表或遗留表：加入对账豁免并写明原因，不得静默忽略漂移。
3. 修改连接池/会话参数：同时验证 Web、Worker、Beat 三种角色。
4. 用户数据删除必须保留审计事实；科研交付 Job 不得用 drop 表清理。
5. 禁止手工改 `uv.lock` 或直接在生产库执行未入库 DDL。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| 会话/引擎 | `src/cygnusx/infrastructure/database/session.py` |
| 模型注册 | `src/cygnusx/infrastructure/database/models/__init__.py` |
| 自定义向量类型 | `src/cygnusx/infrastructure/database/vector.py` |
| 仓储 | `src/cygnusx/infrastructure/database/repositories/` |
| 迁移 | `alembic/versions/` |
| 对账脚本 | `scripts/check_migrations.py`、`scripts/check_schema_drift.py` |

## 关联文档

- 权威基线：[`CygnusX_database_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_database_architecture.md)
- [存储层](storage) · [记忆与知识库](memory-knowledge) · [数据库迁移](../development/database-migrations)
