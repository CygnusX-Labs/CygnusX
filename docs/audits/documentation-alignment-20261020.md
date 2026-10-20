# 文档 ↔ 架构一致性修订报告（2026-10-20）

> **性质**：受控文档修订。依据《[文档 ↔ 架构一致性审核报告（2026-10-20）](doc-architecture-consistency-audit-2026-10-20.md)》，修复 H1–H2、M1–M5、L1–L4 共 11 项问题，并建立可持续的计数校验机制。
>
> **核心原则**：以实际代码和配置为准，以最小改动修正文档；不因文档错误修改运行行为。
>
> **范围**：`ARCHITECTURE_DESIGN/`、`wiki/`、`AGENTS.md`、`Makefile`、`.github/workflows/ci.yml`，新增 `scripts/check_doc_counts.py` 与本报告。未修改 `src/`、`alembic/`、`deploy/`、`data/`、`flows/`、`tool_configs/` 或任何子模块内部文件。

---

## 1. 修订前事实复核

审计报告中的动态数量在修订前全部重新解析，未直接沿用：

| 事实 | 当前值 | 事实源 | 复核方式 |
| --- | ---: | --- | --- |
| ORM 表 | 116 | `src/cygnusx/infrastructure/database/models/*.py` | AST 扫描 `__tablename__` 去重 |
| 模型模块 | 51 | 同上（不含 `__init__.py`） | 文件计数 |
| Alembic 迁移 | 119 | `alembic/versions/*.py` | 文件计数 |
| 镜像清单 | 17 | `deploy/image-mapping.yaml` | YAML `images` 条目计数 |
| 静态 LLM function | 45 | `tool_configs/tools_schema.yaml` | YAML `tools` 条目计数 |
| 前端工具卡片 | 19（18 启用） | `tool_configs/tools_setting.yaml` | 条目计数 + `enabled != false` |
| Studio 工具名 | 28 | `src/cygnusx/application/services/studio_tools.py` | 解析 `STUDIO_TOOL_NAMES` frozenset |
| 安全清单 | 15 | `wiki/security/hardening-checklist.md` | `- [ ]` / `- [x]` 计数 |
| `execution_path` 实际发射值 | 5 | `src/cygnusx/` | 字面量检索；`agentteams_manager_consultation` 无代码赋值 |

同时确认：`agentteams_manager_consultation` 仅存在于测试函数名中；Manager 会诊的事件投影使用 `agentteams_worker_react`。Dataset 七张物理表以 ORM/迁移为准，Handoff 为 `dataset_versions.handoff` JSON 列 + `dataset_analysis_links.handoff_hash`，无独立表。

**历史值识别**：以下内容按历史快照保留，未被改写：

- `CygnusX_database_architecture.md:230`（2026-09-11：88 迁移 / 39 模型模块）；
- `ARCHITECTURE_DESIGN/README.md` 中 2026-07-17 的“Studio 十工具”评审记录；
- `CygnusX_sandbox_architecture.md:305` 的 2026-10-01 施工记录“14 images”（仅追加历史标识，原文未动）。

---

## 2. 修订文件与变更摘要

### 2.1 高优先级

| 文件 | 变更 |
| --- | --- |
| `ARCHITECTURE_DESIGN/CygnusX_database_architecture.md` | 87→116 表（2 处）；模型模块 39→51；迁移 88+→119；`mem0_memories` 改为“引擎已删除、受保护迁移残留、drift 豁免” |
| `ARCHITECTURE_DESIGN/README.md` | 数据库索引段 87→116；补充 `ARCHITECTURE_DISCOVERY_REPORT.md` 索引（L3）；`tools_schema` 43+→静态 45（L2）；`execution_path` 六→五实际发射值（M1） |
| `wiki/README.md` | 数据库条目 87→116 |
| `wiki/architecture/index.md` | 数据库条目 87→116 |
| `wiki/architecture/database.md` | 当前状态 87→116 |
| `wiki/deployment/index.md` | 镜像数量改为“以清单与校验命令为准（当前 17 个）” |
| `wiki/development/project-structure.md` | 同上 |
| `wiki/architecture/sandbox.md` | 同上 |
| `wiki/architecture/overview.md` | 同上 |
| `AGENTS.md` | 87→116 表；14 镜像→“当前 17 个，以清单与 `make validate-image-mapping` 为准” |

### 2.2 中优先级

| 文件 | 变更 |
| --- | --- |
| `ARCHITECTURE_DESIGN/CygnusX_agent_architecture.md` | `execution_path` 改为五个实际发射值，注明 `agentteams_manager_consultation` 为未发射规划值 |
| `ARCHITECTURE_DESIGN/CygnusX_agent_execution_framework.md` | 登记表中该值标为“规划值，未发射”，执行来源置空；补充不得用于排障/告警的说明 |
| `wiki/architecture/agent-runtime.md` | 同上语境修正；Studio 工具“十工具”→“`STUDIO_TOOL_NAMES` 当前注册 28 个工具名” |
| `wiki/architecture/overview.md` | 执行路径说明改为五条实际值 + 规划值注记 |
| `wiki/features/ai-chat.md` | 同上 |
| `wiki/security/index.md` | 安全加固清单 24→15 项 |
| `wiki/research/dataset.md` | 七表枚举改为 `datasets`/`dataset_versions`/`dataset_sources`/`dataset_assets`/`dataset_samples`/`dataset_ingestions`/`dataset_analysis_links`；实体图第七项改为 Ingestion；明确 Handoff 为版本内 JSON 契约 + `handoff_hash`，无独立物理表 |

### 2.3 低优先级

| 文件 | 变更 |
| --- | --- |
| `wiki/features/workflows.md` | 拆分“外部 MCP”与“内置 Chat”两条链：外部含 `cygnusx_get_flow_detail`；内置为 `platform_list_flows` → `cygnusx_prepare` → 确认 → `cygnusx_submit`，无 detail 工具；注明动态 per-flow 工具受 `LEGACY_PIPELINE_TOOLS` 控制 |
| `wiki/development/flow-extension.md` | 同上，分通道描述并补默认开关语义 |
| `wiki/architecture/flow-runtime.md` | 顶部流程图与 AI 接入段同样拆为两条固定链（外部 MCP 含 detail，内置 Chat 无 detail）；第六阶段二次检索发现的同类遗漏，已按同一口径修正 |
| `ARCHITECTURE_DESIGN/CygnusX_flow_architecture.md` | 删除“Chat 内置与外部 MCP 同名单”表述，改为两条固定链 |
| `ARCHITECTURE_DESIGN/CygnusX_toolbox_architecture.md` | 19 工具/18 启用；`tools_schema.yaml` 静态 45 条；动态 Flow 工具由 `FlowToolSchemaCompiler` 运行时生成，不写入该文件 |
| `wiki/features/toolbox.md` | 同上，并保留“以文件为准” |
| `ARCHITECTURE_DESIGN/CygnusX_sandbox_architecture.md` | 在 2026-10-01 施工记录后追加历史快照标识与当前取值指引，原文“14 images”保留 |

### 2.4 治理机制与额外修正

| 文件 | 变更 |
| --- | --- |
| `scripts/check_doc_counts.py` | 新增：解析 10 类结构化事实，校验 24 条注册断言；区分当前断言与历史段落；输出人工复核项 |
| `Makefile` | 新增 `make check-doc-counts` |
| `.github/workflows/ci.yml` | 后端 job 增加文档计数校验步骤（位于 worker 配置校验之后、ruff 之前） |
| `wiki/documentation-maintenance.md` | 新增“自动校验”小节：事实源、断言注册、历史跳过、人工项、CI 入口；发布前检查增加该项 |
| `ARCHITECTURE_DESIGN/CygnusX_agent_framework_baseline.md` | 链接校验发现的既有断链：`docs/26.7.26/...CygnusX...` → `docs/update_info/26.7.26/...OmicHub...`（2 处，含 1 处行内路径） |

> 额外修正不属于 11 项审核发现，但在第六阶段链接校验中暴露，属于同一文档层的最小修复。

---

## 3. 逐项问题状态矩阵

| ID | 问题 | 主要处理 | 状态 |
| --- | --- | --- | --- |
| H1 | 数据库规模 87/39/88+ | 全部现状口径改为 116/51/119；历史行保留 | 已解决 |
| H2 | 镜像写死 14 | Wiki/AGENTS 改为 17 或“以清单与校验命令为准” | 已解决 |
| M1 | `execution_path` 六种 | 文档降为五个实际值；规划值明确标注未发射 | 已解决（文档侧；代码未改） |
| M2 | `mem0_memories` 由 mem0 自管 | 改为受保护迁移残留 + drift 豁免 | 已解决 |
| M3 | 安全清单 24 项 | 改为 15 项，与复选框计数一致 | 已解决 |
| M4 | Studio 十工具 | 改为 28 个已注册工具名 | 已解决 |
| M5 | Dataset 第七表写成 Handoff | 改为 `dataset_ingestions`；Handoff 明确为 JSON 契约 | 已解决 |
| L1 | 内外 Flow 工具链同名单 | Wiki 与架构文档分通道描述 | 已解决 |
| L2 | `tools_schema.yaml` 43+ | 改为静态 45 条 + 运行时动态工具 | 已解决 |
| L3 | 发现报告未被索引 | 收入 `ARCHITECTURE_DESIGN/README.md` §7 并在条目中标注审计快照性质 | 已解决 |
| L4 | “14 images”历史记录 | 保留原文，追加日期与历史快照说明 | 已解决（按要求不改写历史） |

**补充验证**：全库检索未再发现下列现状表述：`87 表`、`39 个模型`、`88+ 迁移`、`43+`、`24 项`、`14 镜像`、`同名单`；仅剩的历史行与历史评审条目均带日期或明确历史语境。第六阶段二次检索另在 `wiki/architecture/flow-runtime.md` 发现并修正两处内外 Flow 工具链混写（顶部流程图与 AI 接入段），修正后再次检索确认无同类现状表述。

---

## 4. 文档自动校验脚本

### 4.1 设计

`scripts/check_doc_counts.py`（仅标准库 + PyYAML，无新依赖）：

1. **结构化事实源优先**：ORM 用 AST 扫描、迁移/模型用文件计数、镜像/工具用 YAML 解析、Studio 工具解析 `STUDIO_TOOL_NAMES`、安全清单数复选框。
2. **注册断言而非全局替换**：只校验 `ASSERTIONS` 表中登记的 `(文件, 正则, 事实)`；新增易漂移事实时显式登记，避免对 Markdown 做粗暴数字替换。
3. **历史识别**：带“历史快照 / 历史记录 / 历史值 / 施工记录 / 复盘 / 回顾”等标记的章节，以及以日期/“当时”开头的行，按历史值跳过并输出 `HIST`。
4. **人工复核项**：语义事实（`execution_path` 实际/规划、Dataset 七表语义、“约 19 个工具”的口径）明确列为人工项。
5. **退出码**：`0` 通过；`1` 断言失败；`2` 事实源解析失败。`--json` 供机器消费，`--strict-scan` 将扫描告警升级为失败。

### 4.2 使用

```bash
make check-doc-counts
# 等价于：uv run python scripts/check_doc_counts.py
```

新增或修改计数类文档时，若断言未覆盖，脚本会输出扫描告警（WARN）或人工复核项；确认口径后在 `ASSERTIONS` 中登记。

---

## 5. 校验命令与真实结果

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `uv run python scripts/check_doc_counts.py` | **PASS**，退出码 0：10 类事实、24 条注册断言、0 条扫描告警；识别 4 条历史值并跳过 |
| 2 | `uv run ruff check scripts/check_doc_counts.py` | All checks passed |
| 3 | AST 解析 `scripts/check_doc_counts.py` | AST OK |
| 4 | PyYAML 解析 `.github/workflows/ci.yml` | OK，jobs：gitleaks / backend / bridge / frontend |
| 5 | 相对链接检查（140 个 Markdown：`ARCHITECTURE_DESIGN/` 45、`wiki/` 62、`docs/audits/` 31、根 `README.md`/`AGENTS.md`；跳过代码围栏与 `deprecated/`） | 686 条相对链接，**0 条缺失**（链接检查中发现并修复 1 个既有断链，见 §2.4） |
| 6 | `git diff --stat -- src alembic deploy data flows tool_configs` | 空：未改运行逻辑、Schema、部署配置或工具注册表 |
| 7 | 子模块状态检查 | `Protocol/FlowFrame`、`pipelines/{ATACFlow,RNAFlow,tools}` 仅有修订前既存脏状态，本次未进入子模块、未提交 |

`check_doc_counts.py` 关键输出：

```text
orm_tables 116 | model_modules 51 | alembic_migrations 119
images 17 | static_tools 45
tools_setting_tools 19 | tools_setting_enabled 18 | tools_setting_groups 6
studio_tools 28 | security_checks 15

结果：PASS（10 类事实，24 条注册断言，0 条扫描告警）
```

人工复核项（脚本显式输出，非失败）：

- `wiki/features/toolbox.md` 的“约 19 个工具、6 个分组”中“约”的语义口径；
- `execution_path` 实际发射值与规划值的语义判定；
- Dataset 七张物理表与 Handoff 非独立表的 schema 语义。

---

## 6. 完整性核对

| 检查项 | 结论 |
| --- | --- |
| 11 项问题均有处理或待决策记录 | ✅ 全部在文档侧解决；代码侧未改 |
| 文档现状表述无相互冲突 | ✅ 全库检索旧口径，仅剩带日期的历史记录 |
| 链接与索引有效 | ✅ 140 个 Markdown、686 条相对链接 0 缺失；README/Sidebar 未受破坏 |
| 图与文字一致 | ✅ 流程图（Flow 双通道）与 Dataset 实体树均按新枚举改写 |
| 历史快照未被破坏 | ✅ 2026-09-11、2026-07-17、2026-10-01 记录保留；仅新增历史标识 |
| 未改运行逻辑/Schema/部署/权限 | ✅ `git diff` 对 `src/ alembic/ deploy/ data/ flows/ tool_configs/` 为空 |
| 规划能力未写成已完成 | ✅ `agentteams_manager_consultation`、内部 describe 能力均明确标注为规划/缺失 |
| 未提交、未触碰子模块 | ✅ 工作区保持原状 |

---

## 7. 尚需架构决策的事项

1. **`agentteams_manager_consultation` 是否真正发射**：当前文档按“五实际值 + 规划值”处理。若观测/告警确需区分 Manager 会诊，应在 `AgentConsultationService` 投影链路真正赋值；否则长期保留规划标注即可。本次未改代码。
2. **内置 Chat 是否补 describe 能力**：内置目录工具 `platform_list_flows` 只返回 id/name/category/version；`LEGACY_PIPELINE_TOOLS=false` 时既无 per-flow Schema 也无 detail 工具。需决定补固定 describe 工具，还是接受能力收缩。
3. **硬计数治理边界**：本次仅登记 10 类事实。MCP preset 数量、Agent YAML/启用数、仓储接口/导出数、技能数量等仍未纳入断言，是否扩展到脚本需产品/架构确认。
4. **历史记录格式统一**：脚本目前用关键词 + 日期启发式识别历史段落。建议统一为 `> 历史快照（YYYY-MM-DD）` 标记，降低误判与维护成本。
5. **`ARCHITECTURE_DISCOVERY_REPORT.md` 长期归属**：已登记为审计快照；是否长期留在 `ARCHITECTURE_DESIGN/`，或按文档治理移入归档目录，需架构负责人决定。
6. **归档文档链接策略**：`CygnusX_agent_framework_baseline.md` 仍链接 `docs/update_info/` 下的历史方案。是否保留这类“现状文档 → 历史档案”的链接，需在文档治理中明确。
7. **“19 工具 / 18 启用”的展示口径**：前端注册表有 1 个禁用项（`phylogenetic-tree`）。Wiki 采用“19 个工具、6 个分组”，架构文档补充“18 启用”；是否统一展示口径可再定。

---

## 8. 工作区说明

修订主体已提交为 `d451c7e1`（`docs: 对齐架构与 Wiki 文档事实并加入计数校验`），包含 §2 的文档、`scripts/check_doc_counts.py`、Makefile 与 CI 入口。第六阶段二次复核新增的 `wiki/architecture/flow-runtime.md` 修正与本报告补记当前未提交：

- 修订前既有的未提交文档与新增 Wiki 页面未被还原、未被覆盖；
- 当前未提交改动仅 `wiki/architecture/flow-runtime.md` 与本报告，可通过 `git diff` 审查；
- 未推送，未进入任何子模块；子模块仅有修订前既存的脏状态。

**结论**：11 项审核问题已在文档侧闭环，计数校验与 CI 入口已建立；运行代码、数据库 Schema、部署配置与权限机制保持原样。
