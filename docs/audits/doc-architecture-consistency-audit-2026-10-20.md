# 文档 ↔ 架构一致性审核报告（2026-10-20）

> **性质**：只读审核。审核期间未修改任何代码或既有文档；本文件是审核结束后按用户要求保存的报告。
>
> **范围**：`ARCHITECTURE_DESIGN/`、`wiki/`（62 页）、根 `README.md`。
>
> **事实源**：当前代码、`tool_configs/`、`flows/`、`deploy/image-mapping.yaml`、`alembic/versions/`、CI/校验脚本。`docs/` 仅作旁证；`ARCHITECTURE_DESIGN/deprecated/` 与提案类文档不作为现状依据。
>
> **结论**：整体贴合度较高。共发现 **11 项**问题：2 项高优先级、5 项中优先级、4 项低优先级。

---

## 一、高优先级（会误导架构判断或部署操作）

### H1. 数据库规模仍按旧口径：87 表 / 39 模块 / 88+ 迁移

| 位置 | 当前描述 | 实际 |
|---|---|---|
| `ARCHITECTURE_DESIGN/CygnusX_database_architecture.md:16` | 87 张业务表 | **116 张** |
| `ARCHITECTURE_DESIGN/CygnusX_database_architecture.md:68` | 87 张 ORM 管理表 | **116 张** |
| `ARCHITECTURE_DESIGN/CygnusX_database_architecture.md:95` | 39 个模型模块、87 表 | **51 个模型模块、116 表** |
| `ARCHITECTURE_DESIGN/CygnusX_database_architecture.md:98` | `alembic/` 88+ 迁移 | **119 个迁移文件** |
| `ARCHITECTURE_DESIGN/README.md:186` | “全量注册 87 表” | **116 表** |
| `wiki/README.md:101` | 87 表 | **116 表** |
| `wiki/architecture/index.md:55` | 87 张 ORM 表 | **116 张** |
| `wiki/architecture/database.md:5` | 87 张 ORM 表 | **116 张** |
| `AGENTS.md:19`（范围外，同源漂移） | 87 表 | **116 表** |

**证据**

- 对 `src/cygnusx/infrastructure/database/models/*.py` 做 AST 统计，`__tablename__` 共 **116** 个。
- 模型文件（不含 `__init__.py`）共 **51** 个。
- `alembic/versions/*.py` 共 **119** 个。
- `scripts/check_schema_drift.py` 是与实际库对账的权威检查，文档中的硬计数不应作为契约。

**说明**

`CygnusX_database_architecture.md:230` 的“88 个迁移与 39 个模型模块”是带日期（2026-09-11）的历史记录，可保留；问题在 16/68/95/98 的**现状口径**。

**建议**

改为 116/51/119；或移除硬编码数字，明确“以 `Base.metadata` 和迁移链为准”。建议增加计数脚本/CI 断言，避免再次漂移。若同步修正 `AGENTS.md`，需单独确认。

---

### H2. 镜像清单写成 14 个，实际 17 个

| 位置 | 当前描述 |
|---|---|
| `wiki/deployment/index.md:25` | `image-mapping.yaml` 14 镜像清单唯一权威源 |
| `wiki/development/project-structure.md:94` | 14 镜像清单唯一权威源 |
| `wiki/architecture/sandbox.md:51` | 14 个镜像的唯一权威源 |
| `wiki/architecture/overview.md:81` | 14 个运行时镜像的唯一权威源 |
| `AGENTS.md:87`（范围外，同源漂移） | 14 镜像清单唯一权威源 |

**实际**

- 解析 `deploy/image-mapping.yaml` 得 **17 个条目**。
- `docs/implementation/cygnusx-phase0b-runtime-integration-implementation.md:59` 已明确提醒：“当前有 17 个条目，不能照搬历史‘14 镜像’说明。”

**影响**

镜像 tag 变更清单、发布前核对会漏项；该文件被文档声明为“唯一权威源”，计数错误会直接误导部署。

**建议**

统一改为 17；或者只写“以 `deploy/image-mapping.yaml` 与 `make validate-image-mapping` 为准”，不再写死数量。

---

## 二、中优先级（事实性偏差）

### M1. `execution_path` 文档列出 6 种，代码中只出现 5 种

**文档位置**

- `ARCHITECTURE_DESIGN/CygnusX_agent_architecture.md:597`
- `ARCHITECTURE_DESIGN/CygnusX_agent_execution_framework.md:127`
- `ARCHITECTURE_DESIGN/README.md:127`
- `wiki/architecture/agent-runtime.md:34`
- `wiki/architecture/overview.md:57`
- `wiki/features/ai-chat.md:17`

**实际**

- 全仓 `src/`、`integrations/` 检索不到 `agentteams_manager_consultation` 字面量。
- `AgentConsultationService` 的事件投影默认回落到 `agentteams_worker_react`：
  `src/cygnusx/application/services/agent_consultation_service.py:149-150,180-181,199-200,214,226,240`。
- `agentteams_room_response_service.py` 同样以 worker 路径为默认。
- 唯一出现该词的是测试函数名 `test_route_clarify_exhausted_degrades_to_manager_consultation`（`tests/unit/test_agentteams_room_response_service.py:1001`），不是实际发射值。
- `docs/architecture/agent-execution-loop-runbook.md:29`（历史档案，范围外）也沿用了该说法。

**影响**

排障/观测按 6 个值过滤时，Manager 会诊路径永远查不到；文档把“意图分类”写成了“已发射的观测值”。

**建议**

二选一：在 Manager 会诊代码路径真正发射该值；或文档降为 5 个实际值，并注明“Manager 会诊当前记录为 `agentteams_worker_react`”。

---

### M2. “`mem0_memories` 由 mem0 自建自管”与记忆架构矛盾

**位置**

- `ARCHITECTURE_DESIGN/CygnusX_database_architecture.md:68` 仍称该表“由 mem0 自建自管”。

**实际**

- mem0 引擎代码已于 2026-08-19 删除；该表是受保护的迁移残留。
- `alembic/env.py` 的 `_NON_ORM_TABLES` 与 `scripts/check_schema_drift.py` 对其豁免。
- 同文档 `:226,237,279,284` 的表述是正确的，仅 `:68` 是旧口径。
- `AGENTS.md:19` 与 `CygnusX_memory_architecture.md:72-82,499-501` 已正确描述“引擎已删除、表与 `MEM0_*` 为迁移残留”。

**影响**

读者会误以为平台仍运行 mem0 引擎，进而误判记忆链路。

**建议**

改为“遗留迁移残留表，无 mem0 引擎；由 drift 脚本豁免”。

---

### M3. 安全加固清单“24 项”，实际 15 项

**位置**

- `wiki/security/index.md:8`：“24 项已知风险修复与生产检查项”。

**实际**

- `wiki/security/hardening-checklist.md` 共 **15 个复选框**：
  - 部署前 5 项（`:8-13`）
  - 身份、权限与数据 5 项（`:17-21`）
  - 运行时与供应链 5 项（`:25-29`）
- 无其他编号风险项。

**建议**

改为 15，或去掉数量描述。

---

### M4. Studio “十工具”，实际注册 28 个工具名

**位置**

- `wiki/architecture/agent-runtime.md:33` 在现状表中称 `studio_chat_loop` 为“十工具”。

**实际**

- `src/cygnusx/application/services/studio_tools.py:140-169` 的 `STUDIO_TOOL_NAMES` 共 **28 个**：
  `sandbox_execute`、`workspace_write/edit/read/list`、`list_available_tools`、`cygnusx_workspace_remember`、`datahub_import`、`platform_result_import`、`artifact_register`、`update_plan`、`pipeline_query`、`knowledge_search`、`browser_navigate/screenshot/click/type/press/close`、`document_inspect/create/edit/convert`、`onlyoffice_status/convert`、`tool_orchestrate`、`ask_user`、`network_request`。

**说明**

`ARCHITECTURE_DESIGN/README.md:165` 也写“10 个”，但明确标注为 2026-07-17 历史快照，属合法历史记录；wiki 当前状态表则不应沿用。

**建议**

改为“28 个 Studio 工具名（按 capability 分组）”，或避免硬计数。

---

### M5. Dataset “七表”枚举把 Handoff 当成物理表

**位置**

- `wiki/research/dataset.md:20`：“共七张表（Dataset、Version、Source、Asset、Sample、**Handoff**、AnalysisLink）”
- `wiki/research/dataset.md:16` 的实体图也把 `DataHandoff` 画成实体。

**实际 ORM 表**

`datasets`、`dataset_versions`、`dataset_sources`、`dataset_assets`、`dataset_samples`、**`dataset_ingestions`**、`dataset_analysis_links`。

- Handoff 是 `DatasetVersion` 上的 JSON 列 `handoff`（`src/cygnusx/infrastructure/database/models/dataset.py:55`）加 `handoff_hash`（`:185`）。
- **没有 `data_handoffs` 表**。
- 第七表 `dataset_ingestions` 定义在 `models/dataset.py:137-140`，承载导入提案与持久预留。

**影响**

按文档写迁移/查询会找不到表，并漏掉真正的第七表 `dataset_ingestions`。

**建议**

枚举与图中将第七表改为 `Ingestion`；Handoff 保留为“版本内 JSON + SHA-256 交接契约”的概念描述。

---

## 三、低优先级（表述/索引问题）

### L1. 固定 Flow 工具链未区分“内置 Chat”与“外部 MCP”

**位置**

- `wiki/features/workflows.md:31`：“AI：list_flows → get_flow_detail → prepare → 人类确认 → submit”
- `wiki/development/flow-extension.md:78`：“`cygnusx_list_flows → cygnusx_get_flow_detail → cygnusx_prepare`”

**实际**

- `cygnusx_list_flows` / `cygnusx_get_flow_detail` 只存在于外部 `mcp-server/tools/flows.py:11,65`。
- 内置 `tool_configs/tools_schema.yaml` 只有 `cygnusx_prepare`（`:917`）与 `cygnusx_submit`（`:935`）。
- 内置目录工具是 `platform_list_flows`，只返回 id/name/category/version（`src/cygnusx/infrastructure/mcp/presets.py:190-201,1761`）。
- `wiki/architecture/mcp.md:35-36` 因明确限定外部表面，表述准确。

**影响**

读者会以为内置 Chat 有 detail 工具；当 `LEGACY_PIPELINE_TOOLS=false` 时，内置端将既无 per-flow Schema 也无 describe 工具。

**建议**

在 wiki 流程页注明“外部 MCP 链路”与“内置 Chat 链路”的差异；若固定化目标包含内置 describe，需要补实现。
当前 `LEGACY_PIPELINE_TOOLS=true` 默认值见 `src/cygnusx/core/config.py:114-117` 与 `.env.example:34-36`。

---

### L2. `tools_schema.yaml` 写成“43+”，实际静态 45 条

**位置**

- `ARCHITECTURE_DESIGN/README.md:198`：“`tools_schema.yaml` LLM function 43+ 动态”
- `wiki/features/toolbox.md:31`：“`tools_schema.yaml` 约 43+ 条目（含动态 Flow 工具）”

**实际**

- `tool_configs/tools_schema.yaml` 的 `tools` 列表为 **45** 项。
- 动态 per-flow 工具由 `src/cygnusx/tools/schema_loader.py:176-214` 在运行时生成（每个 `ai.enabled` Flow 生成 1 个 `cygnusx_prepare_<slug>_submission`），不写在 YAML 中。
- `LEGACY_PIPELINE_TOOLS=false` 时动态 per-flow 工具停止注册。

**建议**

改为“静态 45 条 + 运行时动态 Flow 工具”，或统一写“以文件为准”。

---

### L3. `ARCHITECTURE_DISCOVERY_REPORT.md` 未被架构 README 索引

**位置**

- `ARCHITECTURE_DESIGN/ARCHITECTURE_DISCOVERY_REPORT.md` 存在（审计报告，Run ID `arch-audit-20261018T1940+0800-e78fd1ef`），但 `ARCHITECTURE_DESIGN/README.md` 全文无引用。

**影响**

违反“README 是架构权威库入口”的治理约定，报告难以被发现。

**建议**

在 README 的文档索引中登记，或移入工作区/`docs/` 作为临时产物。

---

### L4. 沙箱文档中的“14 images”是带日期的历史验证记录

**位置**

- `ARCHITECTURE_DESIGN/CygnusX_sandbox_architecture.md:305`：“`validate_image_mapping.py` 通过（14 images）”，上下文为 2026-10-01 的施工记录。

**性质**

历史记录，不属于现状错误，不建议篡改；但容易被误读为当前值。

**建议**

保留原记录，补充一句“当时为 14，当前以 `deploy/image-mapping.yaml` 为准”。

---

## 四、已核验准确的部分

- **MCP 固定化 §11**：`LEGACY_PIPELINE_TOOLS=true` 默认、per-flow 工具仍注册、阶段状态与代码一致；`cygnusx_prepare`/`cygnusx_submit` 定义、确认凭证、30 分钟 TTL、单次消费与幂等语义均与实现吻合（`ARCHITECTURE_DESIGN/CygnusX_mcp_architecture.md:773-862`；`tool_configs/tools_schema.yaml:917,935`）。
- **运行时门禁与证据边界**：`WRITE_RUNTIME_ACCEPTED=False`、`DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`、`worker_paths_verified=false`、Dataset 各开关默认 false；RC04 “PARTIAL / NOT ACCEPTED” 与 `wiki/research/evidence-boundaries.md` 一致。
- **路由/计费默认值**：`dynamic_model_routing_enabled=False`、级联 2 次、升级 1 次、健康窗口 300s、半衰期 600s、provider 探测 60s，与 `src/cygnusx/core/config.py:67-74`、`src/cygnusx/main.py:390-392` 一致。
- **记忆预算**：3200 字节、MEMORY.md 200 条、上下文 8000 字符，与代码一致。
- **日志轮转**：50 MB / 30 天 / zip，Celery 20 MB / 7 天，与 `src/cygnusx/core/logging.py` 一致。
- **数量类事实**：MCP preset 22/10/26/10/28、tools_schema 45、Agent 20 个 YAML/19 个启用、仓储 19 接口/24 导出、技能市场 601/`.agents` 561/已安装 56、`MAX_ACTIVE_SKILLS=10`、资源 200 KB，均与代码/文件计数一致。
- **存储**：单存储根、`StoragePathFactory`、sync 双向对账、幽灵目录清理、`/data/` 字面量守卫，与实现一致。
- **Flow 文档主体**：六段 schema、mtime 热重载、表单/AI 双通道、确认门与幂等、契约漂移拒绝、`fastq_workspace` 校验插件，均与代码一致。
- **根 `README.md`**：未发现过期硬计数；本地链接全部可解析。wiki 侧 587 条链接无断链，README/Sidebar 覆盖完整，文档引用的 make 目标均存在。

---

## 五、补充核验（2026-10-20 完成审计）

1. **根 `README.md` 全文逐段核对**：架构表述、证据边界、部署命令与当前代码/门禁一致；无过期硬计数；本地链接全部可解析。无新增发现。
2. **计数抽查复核**：MCP 22/10/26、Agent 20 份 YAML/19 个启用、19 个仓储接口、工具箱 19 工具/6 分组等，均与代码一致。
3. **mem0 全量检索**：仅 `CygnusX_database_architecture.md:68` 仍是旧口径；其余文档均正确描述“引擎已删除、表与 `MEM0_*` 为迁移残留”。
4. **门禁常量检索**：`WRITE_RUNTIME_ACCEPTED`、`DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED`、`worker_paths_verified` 的文档声明与源码一致，未发现“已放开”的错误表述。

---

## 六、总体建议

1. **根因治理**：H1/H2/M3/M4/L2 都是“在文档里写死可推导的计数”。建议把表数、模型模块数、迁移数、镜像数、工具数改为“以某文件/脚本为准”，或增加 `scripts/check_doc_counts.py` 在 CI 中校验。
2. **区分 as-built 与规划**：M1/L1 属于“文档把目标态写成了现状”。建议统一用 `[已实现]` / `[规划]` 标注，尤其是 `execution_path` 与内置 describe 能力。
3. **修复优先级**：先修 H1/H2（影响架构判断与部署），再修 M1–M5（事实错误），最后处理 L1–L4。

---

## 附录：本次审核的计数证据（只读）

```text
模型模块数（不含 __init__.py）：51
ORM __tablename__ 数：116
alembic/versions/*.py：119
deploy/image-mapping.yaml 条目：17
tool_configs/tools_schema.yaml tools：45
wiki/security/hardening-checklist.md 复选框：15
STUDIO_TOOL_NAMES：28
```

审核期间未修改任何代码或既有文档；本文件为审核结束后按用户要求保存。
