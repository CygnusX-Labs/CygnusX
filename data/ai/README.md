# OmicHub AI Agent 配置与平台挂载指南

`data/ai/` 是 OmicHub 内置 AI Agent、提示词、工具权限、Skill、MCP 绑定和 Studio
运行时配置的声明式根目录。本文说明当前所有内置 Agent 的能力边界，重点记录 RNA-seq
Agent 的组成，并给出创建、挂载、同步和验证 Agent 的标准流程。

所有领域知识库源文件统一存放在 `docs/knowledge/`；目录规范见
`docs/knowledge/README.md`。

## 1. 目录职责

| 路径 | 用途 |
| --- | --- |
| `data/OmicHub.yaml` | 平台启用的内置 Agent 清单；只有加入 `agents.enabled` 的 YAML 才会加载。 |
| `data/ai/*.yaml` | 单个内置 Agent 的身份、能力、模型参数、工具包、Skill、MCP 和运行时声明。 |
| `data/ai/prompts/*.md` | Agent 的权威系统提示词。 |
| `data/ai/prompts/shared/` | 多 Agent 共用协议，由加载器统一追加。 |
| `data/ai/prompts/legacy_agents/` | 迁移前提示词，仅供比对，不参与运行时加载。 |
| `data/ai/tools/*.yaml` | 可复用的最小权限工具包；详细格式见 `data/ai/tools/README.md`。 |
| `data/ai/skill_marketplace/<skill-id>/` | 内置 Skill 的可安装来源和版本元数据。 |
| `data/ai/skills/<skill-id>/` | 已安装到平台运行时、可由 Agent 挂载的 Skill。 |
| `data/ai/mas/` | 多 Agent 编排、路由和工具执行策略。 |
| `data/ai/providers.yaml` | 当前模型提供方实例配置。 |
| `data/ai/provider_templates.yaml` | 内置模型提供方模板。 |
| `data/ai/runtime_images.yaml` | Studio/沙盒运行时镜像定义。 |
| `data/ai/studio.yaml` | Studio 默认运行参数和沙盒配置。 |

所有默认路径由 `src/omichub/core/config.py` 管理，并可通过对应环境变量覆盖。

## 2. 平台加载与挂载链路

内置 Agent 的平台挂载链路如下：

```text
data/OmicHub.yaml: agents.enabled
        │
        ▼
data/ai/<agent>.yaml
        ├── prompt_file ──────► data/ai/prompts/*.md
        ├── tool_packs ───────► data/ai/tools/*.yaml
        │                         ├── builtin_tools
        │                         ├── platform_tools
        │                         ├── mcp_ids + mcp_tools
        │                         └── skill_ids
        ├── mcp_ids/mcp_tools ─► 已注册 MCP Server
        ├── skill_ids ─────────► Skill 市场自动安装并挂载
        └── runtime_profile ───► Studio 运行时镜像/资源配置
        │
        ▼
AgentLoader.load_agent_configs()
        │
        ▼
AgentService.ensure_builtin_agents()
        │
        ▼
数据库 Agent 模板、会话上下文和工具权限
```

关键实现位置：

- `src/omichub/infrastructure/config/agent_loader.py`：读取启用清单、Agent YAML、提示词、
  Tool Pack 和 Studio Runtime Profile，并合并最终声明。
- `src/omichub/application/services/agent_service.py`：将内置 Agent 同步到数据库，安装声明的
  Marketplace Skill，并在会话创建时组装模型、MCP、Skill、工具和交接上下文。
- `src/omichub/main.py`：应用启动时执行内置 Agent 同步。
- `scripts/sync_builtin_agents.py`：不重启服务时手动同步内置 Agent。

读取 Agent 列表也会触发幂等同步。配置中的 `mcp_ids` 和 `skill_ids` 会追加到已存在的内置
Agent；声明 `features.managed_prompt: true` 或 `features.managed_profile: true` 后，对应字段会以
YAML 为权威来源持续同步，避免后台临时编辑造成配置漂移。

## 3. 当前内置 Agent 清单

以下 Agent 均已在 `data/OmicHub.yaml` 的 `agents.enabled` 中启用。

| 配置 / Agent ID | 名称 | 主要能力范围 | 默认入口 | 引擎 / Runtime |
| --- | --- | --- | --- | --- |
| `router.yaml` / `agent-router` | 星尘 AI | 统一理解用户意图，选择专家并组织交接；不替代领域专家执行完整分析。 | Chat | Legacy / `analysis-core` |
| `general.yaml` / `agent-general` | 通用助手 | 需求澄清、研究设计、数据契约、质量控制计划、跨专家协调和综合方案。 | Chat | LangGraph / `analysis-core` |
| `rnaseq.yaml` / `agent-rnaseq` | RNA-seq 分析师 | Bulk RNA-seq 原理咨询、实验设计、QC、差异表达、富集、网络分析、流水线执行与结果解释。 | Studio | LangGraph / `analysis-core` |
| `atacseq.yaml` / `agent-atacseq` | ATAC-seq 分析师 | Bulk ATAC-seq、染色质开放性、实验设计、QC、峰识别、差异可及性、motif/footprinting 与多组学解释。 | Studio | LangGraph / `analysis-core` |
| `scrna.yaml` / `agent-scrna` | 单细胞分析师 | 单细胞质控、整合聚类、细胞注释、Marker、轨迹、通讯和完整分析规划。 | Studio | LangGraph / `analysis-scrna` |
| `scrna_upstream.yaml` / `agent-scrna-upstream` | 单细胞上游与样本质控专家 | FASTQ、Cell Ranger、建库 Chemistry、样本纳入、原始矩阵和上游 QC。 | Studio | LangGraph / `analysis-scrna` |
| `scrna_integration.yaml` / `agent-scrna-integration` | 单细胞整合与聚类专家 | 细胞 QC、双细胞、批次校正、HVG、降维、聚类和 Marker 初筛。 | Studio | LangGraph / `analysis-scrna` |
| `scrna_advanced.yaml` / `agent-scrna-advanced` | 单细胞注释与高级分析专家 | 注释验证、Pseudobulk、通路、可视化、轨迹和细胞通讯。 | Studio | LangGraph / `analysis-scrna` |
| `code.yaml` / `agent-code` | 代码助手 | Python、R、Bash 脚本设计、调试、沙盒执行和可复现性说明。 | Studio | Legacy / `analysis-core` |
| `viz.yaml` / `agent-viz` | 可视化助手 | 统计图、出版级绘图、图表说明、结果报告呈现和绘图脚本。 | Studio | Legacy / `analysis-plot` |
| `shania.yaml` / `shania` | 傻妞 | 通用对话、数据与基因问题、多组学思路和研究陪伴。 | Chat | Legacy / `analysis-core` |
| `mcp_builder.yaml` / `agent-mcp-builder` | MCP 构建师 | 从自然语言生成、测试、注册和审查 MCP Server，支持临时 TTL 与人工复核。 | Studio | Legacy / `analysis-core` |

### 3.1 Agent 工具与 Skill 范围

| Agent | Tool Pack | 主要 Skill |
| --- | --- | --- |
| 星尘 AI | `workspace`, `agentteams_case` | 无固定领域 Skill，主要负责路由和编排。 |
| 通用助手 | `workspace`, `research`, `memory`, `handoff`, `subagents`, `agentteams_case` | BLAST、基因组工具、ATAC、MAF/GISTIC2、突变模式。 |
| RNA-seq 分析师 | `workspace`, `research`, `rnaseq`, `memory`, `handoff`, `subagents`, `agentteams_case` | RNAFlow、DEG、富集、表达矩阵、文库链特异性、WGCNA、rMATS、组织特异基因、GFF/GO/KEGG、FASTQ Screen、交付与 MD5。 |
| ATAC-seq 分析师 | `workspace`, `research`, `atacseq`, `memory`, `handoff`, `subagents`, `agentteams_case` | ATACFlow、ATAC 工具集、基因组工具、差异分析、富集、FASTQ Screen、GFF/GO/KEGG、交付与 MD5。 |
| 单细胞分析师 | `workspace`, `research`, `memory`, `handoff`, `agentteams_case` | 人/鼠与植物注释、流程总览、对象转换、重聚类、参考注释、T 细胞映射、DEG、注释统计、Quarto 报告、scRNA-seq。 |
| 单细胞上游专家 | `workspace`, `research`, `memory`, `handoff`, `agentteams_case` | 当前主要依赖提示词、平台研究工具和专家交接。 |
| 单细胞整合专家 | `workspace`, `research`, `memory`, `handoff`, `agentteams_case` | 当前主要依赖提示词、平台研究工具和专家交接。 |
| 单细胞高级专家 | `workspace`, `research`, `memory`, `handoff`, `agentteams_case` | 注释、对象转换、重聚类、参考映射、T 细胞映射、DEG、统计和报告。 |
| 代码助手 | `workspace`, `development`, `handoff`, `subagents`, `agentteams_case` | 软件管理、日志插件、MD5、数据交付。 |
| 可视化助手 | `workspace`, `visualization`, `handoff`, `agentteams_case` | R 绘图库、DotPlot。 |
| 傻妞 | `workspace`, `research`, `memory`, `handoff` | 无固定 Skill，按通用研究上下文工作。 |
| MCP 构建师 | `workspace`, `memory`, `handoff` | 无固定 Skill，能力由 MCP Builder 配置和审核流程提供。 |

Agent 的能力边界由提示词与实际挂载权限共同决定。只在提示词中写“可以调用某工具”不会产生
权限；必须通过 Tool Pack、`mcp_ids`、`mcp_tools` 或 `skill_ids` 完成真实挂载。

## 4. RNA-seq Agent

RNA-seq Agent 是当前 Bulk RNA-seq 的统一领域入口，配置文件为 `data/ai/rnaseq.yaml`。

### 4.1 能力范围

- **学习与咨询**：解释 RNA-seq 原理、测序设计、重复数、链特异性、批次效应、统计模型和常见误区。
- **方案设计**：根据研究问题、分组、协变量、物种、建库类型和输入文件生成分析计划与数据契约。
- **数据质控**：识别 FASTQ、计数矩阵、表达矩阵和样本表，规划原始数据、比对、定量和样本级 QC。
- **差异表达**：设计比较、协变量和对比矩阵，执行或指导 DEG 分析，并解释效应量、显著性和批次影响。
- **生物学解释**：进行 GO/KEGG 富集、组织特异基因、WGCNA、可变剪接和结果交叉验证。
- **平台执行**：准备 RNA-seq 任务、提交流水线、查询状态和结果，并生成火山图等基础图表。
- **协同交付**：可向代码、可视化或其他领域 Agent 交接，也可创建并行子任务和 AgentTeams Case。

默认输出包括分析计划、DEG 表、通路表和生物学解释。Agent 不应伪造未执行的结果，也不应在
缺少关键元数据时直接给出确定性结论。

### 4.2 RNA-seq 组成

| 资源 | 路径 | 作用 |
| --- | --- | --- |
| Agent 声明 | `data/ai/rnaseq.yaml` | 身份、能力、输入输出、模型参数和全部挂载关系。 |
| 系统提示词 | `data/ai/prompts/rnaseq.md` | 咨询、规划、执行、知识检索和交付规范。 |
| 专用工具包 | `data/ai/tools/rnaseq.yaml` | RNA-seq 内置工具、平台工具、MCP 和白名单。 |
| Skill 市场源 | `data/ai/skill_marketplace/rnaflow/SKILL.md` | RNAFlow Skill 的内置安装来源。 |
| 执行镜像 Skill | `pipelines/tools/skills/rnaflow/SKILL.md` | 流水线执行侧使用的 Skill 镜像。 |
| 已安装 Skill | `data/ai/skills/rnaflow/SKILL.md` | 平台运行时可挂载版本。 |
| 知识导入脚本 | `scripts/import_rnaseq_knowledge.py` | 将 RNA-seq 文档发布并索引到平台知识库。 |
| Agent 同步脚本 | `scripts/sync_builtin_agents.py` | 将 YAML 声明同步到 Agent 数据库。 |

### 4.3 RNA-seq 工具权限

`rnaseq` Tool Pack 按最小权限原则组合以下能力：

- **OmicHub 内置工具**：RNA-seq 任务准备、任务状态和摘要、KEGG 富集、火山图。
- **平台工具**：Flow/Task 查询、工作区文件读取和结果下载。
- **OmicHub Pipelines MCP**：流水线列表、参数检查、RNA-seq 输入准备、提交、状态与结果查询。
- **Ensembl MCP**：物种和组装查询、基因检索、转录本、外部引用、序列和 CDS 查询。
- **GO MCP**：GO 搜索、术语详情、ID 校验和统计。
- **Skill**：通过 `rnaflow` 获取完整执行约定；其他 RNA-seq Skill 由 Agent YAML 直接挂载。

外部 MCP UUID 和允许调用的精确工具名以 `data/ai/tools/rnaseq.yaml` 为准。修改 MCP Server
后应同步更新 `mcp_ids` 和 `mcp_tools`，不要仅依赖服务端自动发现的全部工具。

### 4.4 RNA-seq 知识库

RNA-seq Agent 的提示词要求先检索平台知识库，再使用本地 Skill 和工具执行。导入命令：

```bash
DATABASE_URL='postgresql+asyncpg://...' \
  uv run python scripts/import_rnaseq_knowledge.py \
  --admin-user-id '<管理员 UUID>'
```

导入前可执行预检：

```bash
uv run python scripts/import_rnaseq_knowledge.py \
  --admin-user-id '<管理员 UUID>' \
  --dry-run
```

脚本会创建或更新 `rnaseq` 知识库，发布 `docs/knowledge/rna-seq/RNA-seq.md`，修正文档中的
PDF 链接并重新建立检索分块。知识库负责稳定事实和平台规范，Skill 负责操作流程，实时工具负责
任务状态和实际结果，三者不应相互替代。

## 5. ATAC-seq Agent

ATAC-seq Agent 是 Bulk ATAC-seq 与染色质开放性分析的统一领域入口，配置文件为
`data/ai/atacseq.yaml`。

### 5.1 能力范围

- **原理与实验设计**：染色质开放性、核小体、Tn5、建库、重复、测序深度和参考选择。
- **ATAC 特异质控**：片段周期性、TSS enrichment、FRiP、library complexity、organellar
  reads、blacklist、重复一致性和样本相关性。
- **峰与差异分析**：MACS2/MACS3、pooled peaks、IDR、consensus peaks、峰计数矩阵和差异可及性。
- **调控解释**：peak annotation、GO/KEGG、已知/de novo motif、TF activity、TOBIAS
  footprinting 和 peak-to-gene 关联。
- **多组学整合**：与 RNA-seq 联合建立开放性、TF、靶基因表达证据链，并区分相关与因果。
- **平台执行**：通过 ATACFlow MCP 完成数据检查、预检、确认后提交、状态追踪和结果读取。

### 5.2 ATAC-seq 组成

| 资源 | 路径 | 作用 |
| --- | --- | --- |
| Agent 声明 | `data/ai/atacseq.yaml` | 身份、能力、输入输出、模型参数和挂载关系。 |
| 系统提示词 | `data/ai/prompts/atacseq.md` | 咨询、设计、执行、解释和安全护栏。 |
| 专用工具包 | `data/ai/tools/atacseq.yaml` | ATACFlow、Ensembl、GO、平台任务和结果工具白名单。 |
| 完整流程 Skill | `data/ai/skill_marketplace/atacflow/SKILL.md` | ATACFlow 输入、流程、QC 与平台确认协议。 |
| 专项工具 Skill | `data/ai/skill_marketplace/atac-tools/SKILL.md` | TSS BED 和峰计数矩阵构建。 |
| 知识库源 | `docs/knowledge/atac-seq/` | 3 篇 Markdown、12 个 PDF 和 24 个图片资源。 |
| 知识导入脚本 | `scripts/import_atacseq_knowledge.py` | 全量同步 Markdown 并索引到 `atacseq` 知识库。 |

### 5.3 ATAC-seq 知识库导入

```bash
DATABASE_URL='postgresql+asyncpg://...' \
  uv run python scripts/import_atacseq_knowledge.py \
  --admin-user-id '<管理员 UUID>'
```

预检使用 `--dry-run`。脚本会遍历 `docs/knowledge/atac-seq/**/*.md`，为每篇文档维护稳定 ID、
修订和检索分块；相对附件链接会改写为 `/docs-static/knowledge/atac-seq/...`。PDF 和图片作为
静态附件保留，所有 36 个附件均登记在 `docs/knowledge/atac-seq/README.md`。需要被 AI 检索的
PDF 信息应整理进 Markdown 正文。

## 6. 创建一个新的内置 Agent

内置 Agent 适合需要随代码部署、可审计、可在不同环境重复安装的专家。建议按以下顺序创建。

### 第一步：编写权威提示词

在 `data/ai/prompts/<agent-key>.md` 创建系统提示词，至少明确：

- 身份、服务对象和能力边界；
- 支持的输入和期望输出；
- 工具调用前置条件与禁止事项；
- 何时检索知识库、加载 Skill、调用 MCP 或交接其他 Agent；
- 证据、可复现性、隐私和高风险操作规则。

### 第二步：创建 Agent YAML

在 `data/ai/<agent-key>.yaml` 创建声明。以下模板展示常用字段；字段名和已有 Agent 保持一致：

```yaml
agent_id: agent-example
name: 示例分析师
description: 示例领域的咨询、规划、执行和解释专家。
category: analysis
prompt_file: prompts/example.md

tool_packs:
  - workspace
  - research
  - handoff

skill_ids:
  - example-skill

temperature: 0.4
is_active: true

features:
  engine: langgraph
  managed_prompt: true
  managed_profile: true
  capability_scope:
    - 示例质控
    - 示例统计分析
  accepts_inputs:
    - sample-metadata
    - example-matrix
  produces_outputs:
    - domain-analysis-plan
    - result-table

studio:
  enabled: true
  default_mode: studio
  runtime_profile: analysis-core
  required_capabilities:
    - python
    - statistics
```

建议使用稳定的 `id` 和文件键。Agent 已进入生产数据库后不要随意改 ID，否则同步时会被视为
一个新的 Agent。

### 第三步：加入启用清单

在 `data/OmicHub.yaml` 中把文件键加入：

```yaml
agents:
  enabled:
    - example
```

这里写的是 `data/ai/example.yaml` 的文件名，不是 `agent-example`。

### 第四步：挂载工具能力

优先复用 `data/ai/tools/` 中的 Tool Pack。需要新的权限集合时创建
`data/ai/tools/<pack-id>.yaml`：

```yaml
id: example-analysis
description: 示例 Agent 的最小工具集合。

builtin_tools:
  - omichub_example_tool

platform_tools:
  - list_workspace_files
  - read_workspace_file

mcp_ids:
  - "<已注册 MCP Server UUID>"

mcp_tools:
  "<已注册 MCP Server UUID>":
    - allowed_tool_one
    - allowed_tool_two

skill_ids:
  - example-skill
```

工具类别：

- `builtin_tools`：`tool_configs/tools_schema.yaml` 中注册的 OmicHub 内置函数。
- `platform_tools`：内置 `omichub-platform` MCP 暴露的平台工具。
- `mcp_ids`：已注册 MCP Server 的 UUID。
- `mcp_tools`：每个 MCP Server 对该 Agent 暴露的工具白名单。
- `skill_ids`：随 Tool Pack 一起附加的 Skill。

Agent YAML 可以直接声明 `mcp_ids`、`mcp_tools` 和 `skill_ids`，也可以通过 Tool Pack
复用。加载器会合并并去重；跨 Agent 通用的权限集合应放入 Tool Pack，专属能力可以直接写在
Agent YAML 中。

YAML 不直接执行任意 Python、R 或 Bash。自定义程序必须先注册为内置工具、平台工具或 MCP
工具，保留参数 Schema、认证、审计和确认闸门，再授权给 Agent。

### 第五步：创建并挂载 Skill

Skill 适合承载操作规程、领域工作流和按需读取的参考资料，不适合隐藏不可审计的执行代码。

1. 在 `data/ai/skill_marketplace/<skill-id>/SKILL.md` 创建可安装 Skill。
2. 如该 Skill 还被流水线执行环境使用，在 `pipelines/tools/skills/<skill-id>/` 维护执行镜像。
3. 在 Agent YAML 或 Tool Pack 的 `skill_ids` 中声明 `<skill-id>`。
4. 启动或手动同步时，内置 Marketplace Skill 会自动安装到平台并挂载到 Agent。

运行时先把 Skill 索引提供给模型；模型通过 `use_skill` 按需加载正文，并可继续读取 Skill
声明的资源文件。这能控制上下文体积，避免把长流程全部塞入系统提示词。

### 第六步：注册并挂载 MCP

MCP Server 必须先进入平台注册表，再把返回的 UUID 写入 Agent 或 Tool Pack。

- 管理员接口支持注册、更新、删除、连接测试、工具发现、版本查看和回滚。
- 内置 MCP 预设可通过 MCP 管理接口执行热加载。
- 注册后先测试连接并查看工具列表，再配置 `mcp_tools` 白名单。
- 涉及写文件、提交任务、外部网络或高成本操作时，仅暴露必要工具，并在提示词中定义确认条件。

不要把 MCP 显示名称写进 `mcp_ids`；该字段必须使用平台数据库中的 Server UUID。

### 第七步：选择 Studio Runtime

需要代码执行或大型依赖的 Agent 应指定 `runtime_profile`：

- `analysis-core`：通用分析、RNA-seq 和代码任务；
- `analysis-scrna`：单细胞依赖环境；
- `analysis-plot`：绘图与可视化环境。

新增 Runtime 时，同时更新 `data/ai/runtime_images.yaml` 和相关 Studio 配置，并确认镜像、
CPU、内存、工作目录和持久化策略符合平台安全要求。

### 第八步：同步到平台

应用启动会自动同步。需要立即刷新时执行：

```bash
DATABASE_URL='postgresql+asyncpg://...' \
  uv run python scripts/sync_builtin_agents.py
```

同步后从前台 Agent 列表或管理员 Agent 页面确认：Agent 已启用、提示词版本正确、Skill 已安装、
MCP 已绑定、默认会话类型和 Runtime Profile 正确。

## 7. 创建数据库自定义 Agent

平台同时提供管理员 Agent CRUD，可创建只存在于当前数据库的自定义 Agent：

- `GET /api/v1/admin/agents`：查看全部 Agent，包括停用项；
- `POST /api/v1/admin/agents`：创建 Agent；
- `PUT /api/v1/admin/agents/{agent_id}`：更新 Agent；
- `POST /api/v1/admin/agents/{agent_id}/toggle`：启用或停用；
- `POST /api/v1/admin/agents/{agent_id}/set-default`：设为默认 Agent；
- `DELETE /api/v1/admin/agents/{agent_id}`：删除 Agent。

普通用户通过 `GET /api/v1/agents` 获取已启用 Agent，通过
`GET /api/v1/agents/{agent_id}` 获取详情。

数据库自定义 Agent 适合临时验证和单环境运营配置，但不会自动生成 `data/ai/*.yaml`，也不能
代替代码仓库中的可复现声明。需要长期维护、跨环境部署或随版本发布的 Agent，应回写为内置
YAML；启用 `managed_prompt` 或 `managed_profile` 的内置 Agent 会覆盖数据库中的对应人工修改。

## 8. 交接、多 Agent 与记忆

- 挂载 `handoff` 后，Agent 可使用 `transfer_to_agent` 把结构化上下文交给其他专家。
- 挂载 `subagents` 后，Agent 可使用 `parallel_subagents` 拆分互不依赖的并行子任务。
- 挂载 `agentteams_case` 后，Agent 可创建长期、多角色协作 Case。
- 挂载 `memory` 后，Agent 可保存、更新、删除和检索当前认证用户的长期记忆。
- `memory` 工具始终从认证上下文读取 `user_id`，模型参数不能指定其他用户。

只有确实需要跨会话研究上下文的 Agent 才应挂载长期记忆。交接时应传递研究问题、输入文件、
样本设计、已完成步骤、关键结果、限制和期望产物，不应只发送一句自然语言任务。

### 8.1 Handoff 白名单与路由会话的源 Agent 规范

Agent YAML 顶层的 `handoff:` 段由加载器合并进 `features.handoff`（见
`agent_loader.py`），运行时白名单校验只读数据库中的 `features.handoff`：

```yaml
handoff:
  allowed_targets: ["agent-code", "agent-viz"]  # 或 ["*"] 放行全部活跃 Agent
  max_hops_per_session: 10                       # 可选，默认 10，上限 10
```

- `allowed_targets` 为空或未声明 `handoff:` 段时，该 Agent 发起的所有 `transfer_to_agent`
  都会被拒绝（"目标 Agent 不在当前 Agent 的转交白名单中"）。
- 使用 `"*"` 时仍不能转交给带 `features.router: true` 的路由 Agent。
- 每会话转交次数上限为 10（`max_hops_per_session`，默认值与服务端上限均为 10），第 11 次
  转交会被"本会话最多允许 10 次转交"拒绝。
- 回转交必须携带新增信息：转回本会话历史中曾经作为源出现过的 Agent 时，`reason` 少于
  16 个字符会被拒绝（"回转交必须在转交原因中说明新增信息"）。这两条规则已写入所有挂载
  `handoff` 的 Agent 可见的 `HANDOFF_SYSTEM_PROMPT_SUFFIX`，模型应主动遵守而不是依赖
  服务端报错。
- 提示词中的"当前可转交的 Agent"目录按同一白名单生成，配置变更后须重启或手动同步
  内置 Agent，避免目录与校验结果不一致。

**星尘 AI（agent-router）路由会话的关键约定**：路由入口会话的 `session.agent_id`
恒为 `agent-router`（每条消息重新路由、会话绑定不变），但路由后执行上下文 `ctx` 已切换为
目标专家。因此所有按"当前 Agent"校验的运行时逻辑——包括 handoff 白名单——必须以路由后的
实际执行 Agent（`ctx.agent.agent_id`）为准，严禁使用会话绑定的 `agent_id`。`agent-router`
自身不声明 `handoff:` 段、不挂载 `handoff` Tool Pack；若以会话绑定 Agent 校验，白名单恒为空，
会导致所有专家间转交被拒（2026-08 曾因此全平台转交流转失败，`chat_handoff_events` 零记录）。
参考实现：`chat_service.py` 主流路径的 `ToolInvocationContext(agent_id=str(ctx.agent.agent_id))`。

## 9. 配置校验清单

提交 Agent 变更前至少检查：

- Agent 文件键已加入 `data/OmicHub.yaml`，且 `id` 未与现有 Agent 冲突；
- `prompt_file`、Tool Pack、Skill 和 Runtime Profile 路径均存在；
- MCP UUID 已注册且健康，`mcp_tools` 名称与服务端发现结果一致；
- 写操作、高成本操作和外部网络操作遵守最小权限原则；
- Skill 市场源、运行时安装版本和流水线镜像没有无意漂移；
- `features.accepts_inputs` / `produces_outputs` 与提示词实际承诺一致；
- `studio.default_mode` 与 Agent 是否需要 Studio 执行环境一致；
- 配置同步后，前台可见性、欢迎语、头像、模型参数和工具调用均符合预期。

可执行针对性测试：

```bash
uv run pytest \
  tests/unit/test_agent_loader_studio.py \
  tests/unit/test_agent_router.py \
  tests/unit/test_agent_router_dispatch.py \
  tests/unit/test_prompt_config_contract.py \
  -q
```

## 10. 提示词体积护栏

新增或修改 `data/ai/prompts/*.md` 时，单个提示词超过 120 行必须在 PR 中说明为什么不能下沉到
Skill、知识文件或 Domain Pack。跨 Agent 复用的协议应放入 `data/ai/prompts/shared/`，由加载器
统一追加；稳定领域知识进入知识库，长操作流程进入 Skill，动态状态交给实时工具。
