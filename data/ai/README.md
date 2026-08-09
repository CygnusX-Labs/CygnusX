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
| `data.yaml` / `agent-data` | 数据管理员 | BioOps Case 内部的数据契约、项目元数据、样本表和输入完整性预检。当前为无专用 Skill 的骨架。 | Studio | LangGraph / `analysis-core` |
| `qc.yaml` / `agent-qc` | 质量审计员 | BioOps Case 内部的版本化质量门、Artifact 核验和人工复核分流。当前为无专用 Skill 的骨架。 | Studio | LangGraph / `analysis-core` |
| `delivery.yaml` / `agent-delivery` | 交付报告员 | BioOps Case 内部的交付 manifest、运行说明和证据汇总。当前为无专用 Skill 的骨架。 | Studio | LangGraph / `analysis-core` |
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
| 代码助手 | `workspace`, `handoff`, `subagents`, `agentteams_case` | 软件管理、日志插件、MD5、数据交付。 |
| 可视化助手 | `workspace`, `visualization`, `handoff`, `agentteams_case` | R 绘图库、DotPlot。 |
| 数据管理员 | `workspace`, `memory`, `handoff`, `agentteams_case` | 暂无专用 Skill；后续挂载项目预检与元数据校验 Skill。 |
| 质量审计员 | `workspace`, `memory`, `handoff`, `agentteams_case` | 暂无专用 Skill；后续挂载 QC 规则、任务状态与 Artifact 审查 Skill。 |
| 交付报告员 | `workspace`, `memory`, `handoff`, `agentteams_case` | 暂无专用 Skill；后续挂载交付 manifest、runbook 与证据归档 Skill。 |
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

## 11. 框架现状评估与可优化项

通读加载链路（`agent_loader.py`）、运行时路由（`chat_service.py`）和当前全部 Agent
YAML 后，记录以下值得关注的设计债务，按影响面排序。

### 11.1 LangGraph / Legacy 双执行路径没有在文档中体现

当前 12 个内置 Agent 里，`general`、`rnaseq`、`atacseq`、`scrna`、`scrna_upstream`、
`scrna_integration`、`scrna_advanced` 声明了 `features.engine: langgraph`，其余
（`router`、`code`、`viz`、`shania`、`mcp_builder`、`orchestrator`）没有声明，走
`chat_service.py` 里手写的 legacy 循环。这两条路径对工具调用副作用（`tool_invocations`、
timeline 落库、handoff 事件等）是**各自独立实现**的，历史上已经出现过只改一条路径导致
另一条路径静默丢功能的问题（Plotly 图表卡片刷新后消失）。本文档第 3 节的 Agent 清单
只写了"引擎"列，却没有说明这一区分会带来的实际后果。建议：

- 在第 3 节表格旁补充一句提醒：改动工具调用副作用逻辑时必须确认两条路径都已同步；
- 制定收敛计划，逐步把 `code`/`viz`/`shania`/`mcp_builder` 迁移到 LangGraph，缩小需要
  双写的代码面。

### 11.2 Handoff 白名单一致性校验 ✅ 已解决（2026-08-09）

**曾经的问题**：每个 Agent YAML 手动维护 `handoff.allowed_targets`，随专家增减容易出现
`router.md` 候选表、各 Agent 的 `allowed_targets`、数据库中生效的 `features.handoff`
三处漂移，造成"提示词说可以转交，白名单里其实没有"的静默失败（历史事故见
[[router-session-handoff-source-agent]]）。

**解决方案**：新增 `tests/unit/test_agent_config_consistency.py`，在纯文件层（不触库、
不加载重依赖，全套 <0.2s）做静态回归，覆盖：

- `test_handoff_targets_are_valid_active_agents`：`allowed_targets` 中每个目标（`"*"`
  除外）必须是已启用的 `agent_id`；
- `test_handoff_never_targets_router_or_self`：禁止转交给 `features.router` 的路由
  Agent，也禁止自转交（与 `agent_service._build_handoff_catalog` 运行时语义对齐）；
- `test_handoff_max_hops_within_server_ceiling`：`max_hops_per_session` 必须落在
  服务端上限 `[1, 10]` 内；
- `test_router_prompt_catalog_ids_exist`：`router.md` 候选表中出现的 `agent_id` 必须
  存在于运行时目录，防止提示词引用幽灵专家。

后续增删专家时若忘记同步白名单或候选表，CI 会直接红灯。维护规范见 §12。

### 11.3 模型与 Provider 高度单一化

13 个 Agent YAML 的 `model` 字段全部是 `qwen3.7-plus`，没有按任务复杂度分层（例如给
`router` 这类低延时诉求的入口用更快的模型，给 `mcp_builder` 这类需要强代码生成能力的
用更强模型）。同时 `data/ai/providers.yaml` 里 `deepseek-v4-flash` 和 `qwen3.7-plus`
同时标注 `is_default: true`，虽然同步逻辑（`ai_provider_yaml_loader.py`）只会让最后
生效的一个成为真正默认值，但 YAML 层面两条 `is_default: true` 容易误导后续维护者。
单一 Provider 也是可用性单点故障：一旦 `qwen3.7-plus` 服务异常，全部 Agent 同时不可用。
建议明确模型选型准则，并清理 `providers.yaml` 中重复的 `is_default`。

### 11.4 MAS 编排层全专家登记 ✅ 已解决（2026-08-09）

**曾经的问题**：`agent_capabilities.yaml` 只登记了 `agent-code`/`agent-rnaseq`/
`agent-viz`/`agent-scrna` 四个 Agent，其余 7 个专家（`general`、`atacseq`、三个 scrna
子专家、`mcp_builder`、`shania`）未登记。`mas_plan_validator` 对未登记 Agent 会直接抛
"计划引用了未注册的 MAS Agent"，导致 `settings.mas_enabled` 打开后这些专家在编排器眼里
彻底消失。

**解决方案**：把 `data/OmicHub.yaml` 中 `agents.enabled` 的**全部 11 个专家**补进
`agent_capabilities.yaml`（router 是纯分派入口、orchestrator 是编排器本身，二者不作为
可分派节点，按设计豁免）。登记时的关键机制：

- 能力键是自由词汇表（kebab-case 功能令牌），`mas_plan_validator` 只做"已注册 + 节点
  `required_capabilities` 是能力集合子集"两道校验，不强枚举；
- `flow_registry.agent_capabilities()` 会为 `data/ai/flows/*.yaml` 中 flow 的 `actor`
  （目前 `agent-rnaseq`、`agent-scrna`）自动派生 executor 能力（如 `rnaflow`/`deseq2`/
  `scrna-cellranger` 等）并在加载时并入，因此 actor 型 Agent 只需补充非 executor 的通用
  能力；scrna 三个子专家在 flow 中是 `assistant_agent_id`（不是 actor），拿不到自动派生，
  必须手工登记其分诊/审查能力。

覆盖率由 §11.2 引入的测试保护：`test_all_expert_agents_registered_in_mas_capabilities`
（漏登记即红灯）与 `test_mas_capabilities_have_no_stale_entries`（删专家后遗留孤儿条目
即红灯）。MAS 编排层三个文件的完整职责说明见 §12.1。

### 11.5 工具包与触发词去重 ✅ 已解决（2026-08-09）

**问题一：死工具包 `development.yaml`**。它的 `platform_tools` 与 `workspace.yaml`
完全相同，且经全仓检索确认**没有任何 Agent 引用它**——`code.yaml` 实际用的是
`tool_packs: [workspace, handoff, subagents, agentteams_case]`，README 3.1 表格此前
误写成了 `development`。**处理**：删除 `data/ai/tools/development.yaml`，并修正 3.1 表格。
代码 Agent 的只读上下文能力由 `workspace` 工具包提供，语义不变。

**问题二：触发词冗余**。运行时 `chat_service.py` 的 `_requires_fresh_web_search` 已经把
一份 28 词的公共基线常量 `FRESHNESS_SEARCH_TRIGGERS`（实时/最新/最近/今天/新闻/天气/
文献/论文/研究进展/临床试验/指南/数据库更新/latest/news/pubmed 等）与 Agent 配置的
`triggers` **合并**后再做命中判断（`triggers = [*FRESHNESS_SEARCH_TRIGGERS,
*configured_triggers]`）。因此各 Agent YAML 里凡是落在基线内的词都是纯冗余。**处理**：
把所有 Agent 的 `web_search.triggers` 收敛为"仅基线之外的领域增量词"：

| Agent | 精简后的 triggers |
| --- | --- |
| router / general / rnaseq / shania / orchestrator | `[]`（全部由基线覆盖） |
| code | `[版本, 发布说明, API, 文档]` |
| viz | `[标准, 配色规范]` |
| atacseq | `[方法更新, 软件版本]` |
| scrna | `[细胞图谱]` |

改一个通用时效词现在只需改 `FRESHNESS_SEARCH_TRIGGERS` 一处。规范见 §12.3。

### 11.6 三个 scrna 子专家目前工具能力空心

`scrna_upstream`、`scrna_integration`、`scrna_advanced` 中前两者没有任何
`builtin_tools`/`skill_ids`，仅挂载 `workspace`、`research`、`memory`、`handoff`，
第 3 节表格也如实写了"当前主要依赖提示词、平台研究工具和专家交接"。这意味着这两个
子专家目前无法真正执行任何专项分析，只能对话和转交，实用性有限。建议在文档里明确
这是"设计如此的分诊层"还是"待补齐的过渡状态"，避免后续维护者误以为专属能力已经就位。

### 11.7 提示词体积护栏形同虚设

第 10 节要求超过 120 行的提示词在 PR 中说明理由，但这只是文字约定，没有 CI 校验。
`prompts/mcp_builder.md`（456 行）和 `prompts/visualization.md`（288 行）已经远超
阈值。建议加一个轻量脚本在 CI 里统计提示词行数并输出提醒（不阻断合并），让这条护栏
真正可执行。

## 12. MAS 编排层与配置维护规范

本节沉淀 §11.2 / §11.4 / §11.5 解决后必须持续遵守的约定，避免同类问题复发。

### 12.1 MAS 编排层（`data/ai/mas/`）职责

MAS（Multi-Agent System）编排层仅在 `settings.mas_enabled` 打开时进入内置 Agent 同步
（`agent_loader.py` 会动态把 `orchestrator` 追加进 enabled）。默认关闭，普通聊天入口
不暴露计划工具。三个文件各司其职：

| 文件 | 消费方 | 作用 |
| --- | --- | --- |
| `agent_capabilities.yaml` | `MASPlanValidator` | 声明每个可分派专家的能力集合；校验计划节点的 `agent_id` 已注册且 `required_capabilities` 是其子集。 |
| `artifact_schemas.yaml` | `MASPlanValidator` | 声明 Artifact 类型及 producer；校验下游消费的产物类型确由上游产出（`user_upload` 型可作为根输入）。 |
| `tool_policies.yaml` | `schema_loader` | 按 `tool_key` 声明沙盒执行策略（允许镜像、可写根、是否联网/特权/挂 docker socket）。 |

能力来源有两条并轨且自动合并：**手工登记**（本表的 `agents:` 段）+ **自动派生**
（`flow_registry.agent_capabilities()` 为 `data/ai/flows/*.yaml` 中 flow 的 `actor`
派生其 stage executor 的 `key`）。同一 `agent_id` 两者取并集。

### 12.2 增删专家时的 MAS / handoff 同步清单

新增或删除一个专家 Agent 时，除第 6 节的 8 步外，必须同步：

1. **MAS 能力登记**：在 `agent_capabilities.yaml` 的 `agents:` 段增/删该 `agent_id`
   （router/orchestrator 除外）。actor 型专家只补非 executor 通用能力，executor 能力
   由 flow YAML 自动派生；`assistant_agent_id` 型（如 scrna 子专家）须手工登记全部能力。
2. **handoff 白名单**：检查其它专家的 `handoff.allowed_targets` 是否需要增删该目标；
   目标不能指向 `features.router` 的 Agent，也不能自转交，`max_hops_per_session` ∈ [1,10]。
3. **路由候选表**：同步 `prompts/router.md` 的候选专家表格（`| agent-xxx | 名称 | 适用请求 |`）。
4. **回归验证**：`uv run pytest tests/unit/test_agent_config_consistency.py -q`
   会一次性校验上述 1~3 的一致性；漏改即红灯。

`test_agent_config_consistency.py` 是这套契约的守门员，任何一处漂移都会被它拦下。

### 12.3 web_search 触发词规范

- 通用时效词（最新/文献/论文/今天/news/pubmed 等）由运行时常量
  `FRESHNESS_SEARCH_TRIGGERS`（`chat_service.py`）统一提供，**禁止**在 Agent YAML 里
  重复声明；要调整通用词只改这一处常量。
- Agent YAML 的 `web_search.triggers` **只声明该领域特有、且不在基线中的增量词**
  （如 scrna 的"细胞图谱"、code 的"发布说明/API"）。没有领域增量词时写 `triggers: []`。
- 运行时命中判定用的是基线与 Agent 增量词的并集，因此增量词留空不会削弱通用时效检索。

### 12.4 工具包（`data/ai/tools/*.yaml`）去重原则

- 新建工具包前先确认没有既有包已覆盖同一权限集合；`workspace`（只读浏览当前用户工作区）
  是通用基础包，代码/开发类 Agent 直接复用它，不要再造内容雷同的包。
- 工具包必须至少被一个 enabled Agent 的 `tool_packs` 引用；无人引用的包应删除，避免像
  历史上的 `development.yaml` 那样成为误导维护者的死文件。

## 13. 多智能体协作可运行性核查（2026-08-09）

本节记录对平台**三条多智能体路径**真实可运行性的核查结论，回答"能不能真的跑起来"以及
"是否满足'在 AI 助手/工作台页像群里聊天一样多专家协作、遇决策问用户'的诉求"。核查基于对
后端服务、Celery 任务、前端流解析与组件、独立部署目录的通读，结论均标注了代码位置。

平台目前有**三条形态不同**的多智能体路径，不要混为一谈：

| 路径 | 形态 | 默认开关 | 执行位置 | "群聊"含义 |
| --- | --- | --- | --- | --- |
| **对话内 fan-out**（`parallel_subagents`）| 一次工具调用并行派生 ≤4 个子专家跑受限工具循环 | 管理端 `subagent_fanout_enabled` / env | web 进程内（chat 循环）| 同一会话内并行，非轮流发言 |
| **超频模式**（overdrive room）| Manager + 多 worker 在一个"团队房间"分头像发言 | 前端 `OverdriveToggle` | web 进程内 | ✅ 唯一原生"多专家分头像发言"形态 |
| **MAS 编排**（orchestrator + DAG）| 生成可确认计划 → Celery worker 执行 DAG 节点 | `mas_enabled`（默认 **关**）| Celery worker | 无群聊，卡片式计划+进度 |
| **AgentTeams Case** | 跨角色工作流状态机 + 人工审批 + 交付 | bridge/gateway/chat_entry（默认 **全关**）| 独立部署的 Bridge+Worker 集群 | Matrix/Element 外链聊天室（给人用）|

### 13.1 MAS 编排：执行闭环完整，但默认关闭且有一处隐性断点

**结论：不是"仅预览"。** 从"用户确认计划"到"Celery worker 真实执行节点、产物落库、推进
DAG 直至终态"的代码路径完整存在且相互衔接。

- `mas_plan_preview` 工具（`mas_plan_adapter.py`）确实**只做校验+回传预览卡片**，明写"用户
  确认前不会创建或执行 Run"；但其后有真实执行链：前端"确认并开始执行"→ `POST /mas/runs`
  建 run（`awaiting_approval`）→ `POST /mas/runs/{id}/approve`（`mas_service.py`，未确认草稿
  绝不执行）→ 写 outbox 事件 → Celery Beat 定时 `publish_outbox`(10s)/`consume_events`(5s)
  → `MASEventConsumerService` → `mas_scheduler_service.dispatch_ready_node` → **`enqueue_task`
  真正投递 Celery 任务** → worker 跑 RNAFlow/volcano/quality-gate/EBI/scanpy 执行器，写
  artifact 落库、推进节点状态。
- 状态全程持久化：迁移 `x2y3z4a5b6c7_add_mas_runs_artifacts_events.py` 建 7 张表，仓储用
  乐观锁（`version` + CAS rowcount==1）保证 exactly-once。
- 测试 `tests/unit/domain/mas/test_scheduler.py` 覆盖执行态转移（dispatch once / 成功完成 /
  失败退避重试），不止预览。

**为什么"默认看不到执行"（门控，非代码缺失）**：

1. `mas_enabled` 默认 `False`（`core/config.py`），`.env.example` 也是 `false`；关闭时 API
   全部 403、Chat 不挂预览工具、orchestrator 不加载。
2. 执行是异步的，依赖 **Celery Beat + Worker + Redis Stream 三者常驻**；未起则 `approve`
   后 run 停在 `queued`、事件停在 `pending`（故意保留待重放）。
3. RNAFlow 执行器依赖 `mas_apptainer_image`（**默认空串**）+ apptainer 二进制；EBI/scanpy 依赖
   各自二进制/镜像。纯 Python 执行器（volcano/quality-gate/fake）无外部依赖，可直接跑通。

**⚠️ 隐性断点（真实 bug，建议修）**：`mas_scheduler_service.py:109-132` 的 `dispatch_ready_node`
只对 6 种已知 executor（`fake`/`apptainer-rnaflow`/`deg-volcano`/`quality-gate`/`ebi-download`/
`scanpy-qc`）投递 Celery 任务，但**末尾无条件 `return True`**。若计划节点的 `resources.executor`
不在白名单，节点会被标 `dispatched`（`:100`）却不投递任何任务，且返回 True 假装成功 →
**该节点永久悬挂、run 永不终结、无任何告警**。

**HITL 决策**：MAS 运行时**不复用 `ask_user`**，而是走独立的 **approval 机制**（计划确认
`approve_run`；运行中节点失败/质量门未过 → `create_approval` + run→`paused_for_input`，前端
审批卡恢复或终止）。`ask_user` 只覆盖"进入 MAS 之前"的聊天期澄清。

### 13.2 AgentTeams Case：真引擎在独立部署目录，主栈不含

**结论：这是"跨角色工作流状态机"，不是"多个 LLM 在一个会话里轮流发言"。** 主仓库
（OmicHub）内**只有 HTTP 代理**，真正的执行引擎在 `integrations/agentteams/`（独立可部署的
Bridge + Gateway + Worker 集群），默认三个开关全关、不随主栈启动。

- `AgentTeamsService` 全部方法是对外部 Bridge 的 `httpx` 转发；`create_agentteams_case` 工具
  经确认卡（带 token、10 分钟窗口，模型无法伪造 `_confirmed` 直接建 Case）后，最远只能把 Case
  推到 `approval_pending`，之后的执行/质量/交付全靠 `integrations/agentteams/worker/` 里的独立
  轮询进程 + 人工在 `AgentTeamsCaseView.vue` 审批提交。
- 主仓库 Celery 里的 `watch_cases`(60s) **只做状态回流通知，不推进 Case**。
- **"多角色轮流"= Work Item 派发 + Worker 轮询认领**（`while True: run_once(); sleep()`），
  角色间不通过自然语言互相回复；grep `speaker/turn/round/groupchat` 无命中。
- **"群聊室"= Matrix/Element**：`AgentTeamsChatDrawer.vue` 只内嵌一个 Element iframe /
  新窗口打开 Element URL，是**给人参与的聊天室**，不是产品内原生的多 LLM 群聊。
- 前端 UI 完成度高（生产级非 mock）：`AgentTeamsCaseView.vue`（503 行，5 阶段步骤条 / 工作项 /
  实时时间线 SSE+轮询降级 / 审批弹窗）+ 路由 + 管理台 Bridge 配置页。
- **持久化边界**：Bridge Case 存 Redis 快照/文件，"生产级数据库存储仍是后续工作"；Case/Work
  Item/事件**不落主库**，主库只有 `agentteams_bridge_settings` 一张配置表。

**随附 Worker 是验收骨架**：仓库内 Worker 仅在 demo 开关 + `agentteams-acceptance-` 前缀 + 只读
工作项时自动完成，生产执行需接入真实分析 skill 与 Gateway LM 咨询后端。

### 13.3 ask_user 决策询问链路：三条路径打通，fan-out 缺一环

`ask_user` 从后端到前端弹窗的链路是**打通**的：工具 schema 在 `studio_tools.py`，SSE 统一为
`type="ask_request"`，前端 `useAgentChatStream.ts` 有 `case 'ask_request'` → store 落位 →
`AskUserCard.vue`（分页问题向导，支持点选/「其他」自由输入/跳过）弹窗，答案作为下一条 user
消息回灌续跑（文本回灌而非专用回调端点，但闭环）。

| 执行路径 | ask_user 弹窗 |
| --- | --- |
| 普通 chat | ✅ 打通（schema 兜底挂载 + legacy/LangGraph 两条循环都发 ask_request）|
| Studio 工作台 | ✅ 打通（`AskUserModal` 复用 `AskUserCard`）|
| 超频模式（overdrive room）| ✅ 打通（intake / worker / followup 三处发 ask_request）|
| **对话内并行子 Agent（`parallel_subagents`）** | ⚠️ **未打通** |

**fan-out 的 ask_user 缺口**：子 Agent 调 `ask_user` 时被转成 `needs_user_input` packet，聚合进
汇总文本回灌给上级模型，**前端不会弹窗**（对话内 fan-out 只发 `type="subagents"`，不把子问题
再发成 `ask_request`）。即"并行分析时子专家无法直接向用户求决策"。

### 13.4 与"页内群聊式多专家协作"诉求的差距

用户诉求：在 AI 助手/工作台页，**像群里聊天一样**多专家协作分析，**遇决策问用户**。逐条对照：

1. **群聊有雏形但入口分裂**：真正的"多专家分头像发言"只在**超频模式**（overdrive room，
   `room_speech`/`room_speech_delta` SSE + `KimiMessageItem.vue` 发言者头像徽标）下成立；普通
   对话默认单 Agent + handoff 徽标。且 worker 发言默认被折叠成"阶段产物"，不像自然群聊平铺可读。
2. **对话内并行子 Agent 无群聊/泳道展示**：后端在 `chat_service.py:5603/5647` 发 `type="subagents"`
   （started/aggregated），但前端 `useAgentChatStream.ts` **没有 `case 'subagents'`**，事件被直接
   丢弃。用户看不到"哪几个专家在并行、各自进度"——最明显的可视化空洞（记忆
   [[parallel-subagent-fanout]] 记的"前端泳道卡片未做"仍属实）。
3. **fan-out 里的 ask_user 无法冒泡**（见 §13.3），直接违背"遇决策问用户"。
4. **AgentTeams 群聊是外链 Element iframe**，非产品内原生群聊，默认关闭，体验割裂。
5. **handoff 缺"切换过场"可视化**：只有"本条由专家X回答"的静态徽标，无"从 A 切到 B"的过场。

**一句话总结**：用户想要的"多个 LLM 专家在页面群里聊天式分析"这个具体形态，**最接近的是
超频模式的 room_speech**，但它入口隐蔽、可读性弱；对话内 fan-out 有后端能力却缺前端展示与
ask_user 冒泡；AgentTeams 的群聊则是外部 Element。三者都还不是开箱即用的"页内多专家群聊"。

### 13.5 可优化项（按投入产出比排序）

1. **补 `subagents` 事件的前端渲染（最高性价比）**：在 `useAgentChatStream.ts` 增
   `case 'subagents'`（started 建泳道、aggregated 落终态），store 加 `onSubagentFanout`，用类似
   `OverdriveProgressCard.vue` 的多 Agent 泳道卡片展示。后端能力已就绪，纯前端工作即可点亮
   "并行专家可视化"。
2. **打通 fan-out 的 ask_user 冒泡**：在对话内 fan-out 聚合处检测子 Agent 的
   `needs_user_input`/`awaiting_input`，命中则额外 `yield type="ask_request"`（复用现成
   `AskUserCard`）并暂停 fan-out 等待回答。
3. **修 MAS 未知 executor 静默悬挂**（§13.1）：`dispatch_ready_node` 对不在白名单的 executor
   应显式标 `NODE_FAILED`（如 `UNKNOWN_EXECUTOR`）并记事件，避免节点永久卡 `dispatched`。
4. **统一群聊入口与可读性**：让 AI 助手页在多专家参与时也默认走 `room_speech` 群聊气泡（不限
   超频模式），并给 worker 发言提供"默认展开正文"选项，贴近真实群聊观感。
5. **MAS/AgentTeams 常驻看门狗与对账**：MAS 加 beat 巡检回收超时未推进的节点/run；AgentTeams
   把 `reconcile_case` 从"用户查看时触发一次"升级为 beat 定时对活跃 `executing` Case 主动对账，
   避免用户不打开页面就卡住。
6. **handoff 过场卡片（轻量）**：基于已到位的 `handoff` 事件（含 source/target 名与 reason），在
   消息流插一条"专家 A → 专家 B（原因…）"过场，而非仅静态徽标。

> 说明：本节为只读核查结论，未改动任何后端/前端代码；§13.5 是建议清单，需另行立项实施。
> MAS 与 AgentTeams 均默认关闭，启用方式与部署前置见 `.env.example` 与
> `deploy/agentteams/README.md`、`docs/configuration/多Agent协作配置指南.md`。

## 14. 统一超频协作架构（实现蓝图 · 分支 `feature/unified-overdrive-agent-team`）

本节是把 §13 的核查结论转化为**可施工的实现方案**。目标一句话：**把"对话内
fan-out"、"AgentTeams Case"两条路径都收敛进"超频模式"这一个心智模型——即"一个
Manager 管理的专家 Agent 团队，在页内以群聊形式协作，遇决策问用户"**。MAS DAG 执行
作为超频的"重型执行后端"之一被复用，不再是并列的第三种入口。

### 14.1 统一心智模型

对用户只暴露**一个概念**：超频模式 = Manager 带队的专家团队。用户在 AI 助手/工作台页
打开超频开关（或说"用团队处理"），后续所有多专家协作都表现为**同一套群聊 UI**：

- **Manager**（人格沿用当前会话绑定的 Agent，通常是星尘 AI）负责澄清、分工、汇总；
- **专家 worker**（平台现有 `agent-rnaseq`/`agent-code`/`agent-viz` 等）在群里分头像发言；
- 遇到需要用户拍板的决策点，任何成员都能弹 `ask_user` 卡片问用户；
- 用户不需要知道底层走的是 fan-out、DAG 还是 AgentTeams Case——这些是**执行档位**，
  由 Manager 按任务复杂度和 §13 的 `collaboration_preset` 自动选择。

**执行档位与现有 `collaboration_preset` 对齐**（`site_settings_service.py:198-214` 已实现）：

| 档位 | preset | 底层执行后端 | 何时用 |
| --- | --- | --- | --- |
| 会诊/轻量 | `light` | 多专家会诊（consult）| 咨询、方案评估 |
| 并行团队 | `parallel` | **对话内 fan-out**（`ParallelSubAgentService`）| 2–5 个可独立完成的短子任务 |
| 全流程闭环 | `full` | **AgentTeams Case**（跨角色审批+执行+交付）| 需审批、正式执行、质控交付 |
| DAG 工作流 | （`mas_enabled`）| **MAS 编排**（Celery worker 执行 DAG）| 分钟–小时级流水线 |

超频房间是**统一前台**；上表右列是它可调度的**执行后端**。Manager 的分工结果决定把每个
worker 任务投递到哪个后端——但对前端和用户，全部表现为群聊气泡 + 泳道进度 + 决策卡片。

### 14.2 为什么可行：三条路径已共享同一执行内核

§13 与本轮深挖确认了统一的地基（关键事实，均已核对）：

- **worker 执行引擎只有一套**：`ParallelSubAgentService`（`parallel_subagent_service.py`）。
  fan-out、超频房间、Goal fanout adapter 三个"编排外壳"已经都调它跑受限 ReAct 子循环。
  统一后 AgentTeams Case 作为第四个消费方接入，执行内核不重写。
- **群聊 UI = 消息气泡 + `senderAgent` 皮肤**，不是独立房间组件。`ChatMessage.senderAgent`
  （`types.ts:123`，带 `role: manager|worker`）+ `OverdriveProgressCard.vue`（`tasks[]` 泳道）
  + `AskUserCard.vue`（决策弹窗）三件套已就位，任何"多角色发言"复用它即可。
- **分层骨架已存在**：`collaboration_preset`（`custom|light|parallel|full`）+ 四个能力开关
  （`site_settings_service.py`）已经是现成的档位系统，超频只需按档位选执行后端。
- **统一事件模型已有雏形**：SSE `ChatChunk = {type, content, metadata}`（自由 dict 透传，
  `openai_compatible.py:130`），前端已处理 `room_speech`/`overdrive_progress`/`ask_request`/
  `agentteams_case` 等 case（`useAgentChatStream.ts`）。缺的主要是 `subagents` case。

### 14.3 分阶段实现方案

按"可独立验证、后端能力优先、风险从低到高"排序。每阶段可单独合并、单独回归。

#### 阶段 A：fan-out 接入超频群聊 UI（纯前端，最高性价比）

后端已发 `type="subagents"` chunk（`chat_service.py:5602` started / `:5646` aggregated），
前端整段丢弃。补齐即可让"并行团队"档位在群里可见。

- `subagents` chunk 字段（已确认）：
  - started：`{phase:"started", tool_call_id, tasks:[{index, agent_id, task}]}`
  - aggregated：`{phase:"aggregated", tool_call_id, success, summary, progress:[{index, agent_id, status, elapsed_s}]}`
- 前端改动：
  1. `useAgentChatStream.ts` 增 `case 'subagents'`，解析 started/aggregated，回调 `onSubagentFanout`。
  2. `agentHub.ts` 增 `onSubagentFanout`：started 时按 `tool_call_id` 建一条 `role=system` 的
     进度消息，映射进 `OverdriveProgress`（字段适配：`index→taskId`、`agent_id→agentId`、
     `status` 直传）；aggregated 时更新每个 task 终态 + 落 `summary`。
  3. 复用 `OverdriveProgressCard.vue` 的 `tasks[]` 泳道渲染；给它加一个 `readonly`/`hideControls`
     prop，隐藏超频专属的暂停/终止/指令条（fan-out 无 `controlOverdrive` 语义）。
- 验收：开启 `subagent_fanout_enabled`，让通用助手并行派 2 个子专家，页面出现多 Agent 泳道
  卡片，每个专家的状态从 running→succeeded 实时更新。

#### 阶段 B：打通 fan-out 的 ask_user 冒泡（后端）

fan-out 子专家遇决策时，`parallel_subagent_service.py:496` 已把 packet 标 `awaiting_input`
并带 `needs_user_input`，但对话内 fan-out 路径只发 `subagents` chunk、不转成 `ask_request`。

- 后端改动：在 `chat_service.py:5646` 附近，检测 `fanout_envelope.ui_payload.progress` 里存在
  `status in {awaiting_input, approval_pending}` 的子任务，或 `llm_payload` 标 `needs_user_input`，
  命中则额外 `yield ChatChunk(type="ask_request", metadata={... questions ...})`，并**暂停本轮
  fan-out**（沿用超频 worker 澄清的既有语义，见 `chat_service.py:3729` 那条路径）。
- 用户答完 → 现有 `answerAskRequest`（`agentHub.ts:2307`）把答案作为下一条 user 消息回灌 →
  fan-out 续跑。
- 验收：并行子专家中有一个调 `ask_user`，前端弹 `AskUserCard`，答完后该子任务继续。

#### 阶段 C：把 AgentTeams Case 包装成超频房间的"全流程闭环"档位（后端为主）

这是本目标的核心。当前 Case 有独立的确认卡（`AgentTeamsCaseCard.vue`）+ 独立页
（`AgentTeamsCaseView.vue`），与超频群聊是两套 UI。统一做法：**让 Case 生命周期事件映射成
超频房间的群聊发言 + 泳道进度**，用户在同一个群里看到 Case 推进。

- **事件适配层（新增）**：`AgentTeamsService.stream_case_events`（`agentteams_service.py:344`）
  已能流式吐 Case 审计事件（`case.created`/`work_item.assigned`/`skill.finished`/
  `approval.requested`/`quality.decision`/`case.closed` 等，见 `AgentTeamsCaseView.vue:137-152`）。
  新增一个 `CaseRoomProjector`：把这些事件翻译成超频 SSE：
  - `work_item.assigned` → `room_speech`（sender = 对应角色 Agent，如 data-steward/workflow-operator，
    role=worker）+ `overdrive_progress`（该 work_item 一条泳道）；
  - `approval.requested` → `overdrive_approval_request`（复用现成审批卡
    `OverdriveApprovalCard.vue`）或 `ask_request`（决策询问）；
  - `skill.finished`/`quality.decision`/`case.closed` → `room_speech`（Manager 汇报阶段结论）。
- **角色即 senderAgent**：AgentTeams 的角色（Manager / Data Steward / Workflow Operator /
  Quality Auditor / Delivery Reporter）映射为 `senderAgent`（复用 §14.2 的气泡渲染），
  用平台 Agent 头像/名字/颜色。这样 Case 也表现为"群聊里多角色发言"。
- **人工审批 = 决策询问**：Case 到 `approval_pending` 时，projector 发 `overdrive_approval_request`；
  用户在群里点批准 → 调既有 `approve_and_submit_task`（`agentteams_service.py:244`）推进。
  与超频 `approve_overdrive_approval`（`chat.py:66`）语义统一，前端复用同一审批卡。
- **驱动**：Case 状态推进仍由外部 Bridge/Worker 负责（§13.2，不改执行边界）；OmicHub 侧新增
  一个"房间投影订阅"——在超频房间内订阅 `stream_case_events`，把事件实时投影成群聊 SSE。
  Celery `watch_cases`（`tasks/agentteams.py:25`）从"只回流通知"升级为"投影到房间 + 触发对账"。
- **触发**：Manager 判定任务属"全流程闭环"（`collaboration_preset=full` 且 Bridge 已配）时，
  在超频房间内调 `create_agentteams_case`（经确认卡），Case 建成后房间自动订阅其事件投影。
- 验收（需 Bridge 部署，见 §13.2）：超频房间内发起一个正式分析 Case，群里依次出现"Manager
  分派 → 各角色领取工作项 → 请求审批（用户在群里批准）→ 质控 → 交付"的发言与泳道推进。

#### 阶段 D：统一入口与可读性（前端体验）

- AI 助手页在**任意多专家参与**时（fan-out/Case/超频）都走 `room_speech` 群聊气泡，弱化
  "只有开超频才有群聊"的割裂感；`OverdriveToggle` 语义升级为"团队协作模式"。
- worker 发言提供"默认展开正文"选项（当前折叠成"阶段产物"，`KimiMessageItem.vue`），贴近
  真实群聊观感。
- handoff 增加轻量过场卡片（专家 A → 专家 B + reason），基于已到位的 `handoff` 事件。

#### 阶段 E：健壮性（后端，可与 A–D 并行）

- 修 §13.1 的 MAS 未知 executor 静默悬挂：`mas_scheduler_service.py:109-132` 末尾对白名单外
  executor 显式标 `NODE_FAILED`。
- MAS/AgentTeams 常驻看门狗：beat 巡检回收超时未推进的节点/Case。

### 14.4 统一 SSE 事件契约（施工须遵守）

所有执行后端投影到超频房间时，**只准使用以下既有 chunk 类型**，不新造前端不认识的类型：

| chunk type | 用途 | 前端消费点 |
| --- | --- | --- |
| `room_speech` / `room_speech_delta` | 成员发言（Manager/worker/Case 角色）| `useAgentChatStream.ts:549/574` |
| `overdrive_progress` | 泳道进度（tasks[] 状态网格）| `:593`（fan-out 经阶段 A 适配后复用）|
| `ask_request` | 决策询问（任何成员）| `:744` → `AskUserCard.vue` |
| `overdrive_approval_request` | 需批准的高风险操作 | `:624` → `OverdriveApprovalCard.vue` |
| `mode_changed` | 进入/退出超频 | `:546` |

新增执行后端（如 Case projector）必须把自身事件翻译成上表类型；`senderAgent` 用平台 Agent
身份填充。这是"一套 UI 承载所有协作形态"的硬约束。

### 14.5 落地顺序与风险

- **阶段 A/B/E 不依赖外部部署**，可直接在本分支实现并单测回归——优先做，立刻点亮"并行团队
  群聊 + 遇决策问用户"，覆盖用户诉求的主体。
- **阶段 C（AgentTeams 包装）依赖 Bridge 部署才能端到端验证**（§13.2 三开关默认关），但
  `CaseRoomProjector` 事件适配层本身可先实现 + 用 mock 事件单测。
- **阶段 D 是纯体验优化**，可最后做。
- 所有改动遵守 [[langgraph-vs-legacy-dual-path]]：涉及工具副作用/SSE 的逻辑，legacy 与
  LangGraph 两条路径都要改。改完 `docker restart omichub-web`（[[omichub-web-no-autoreload]]）。

> 本节为实现蓝图，供分阶段施工与评审。阶段 A/B/E 为纯内部改动可即时验证；阶段 C 的端到端
> 依赖 AgentTeams Bridge 部署（默认关闭）。

## 15. 实现进度（分支 `feature/unified-overdrive-agent-team`）

> 最后更新：2026-08-09。下列状态均经回归测试和类型检查验证。

### 15.1 ✅ 已完成：阶段 E — MAS 未知 executor 静默悬挂修复

**问题**：`MASSchedulerService.dispatch_ready_node`（`mas_scheduler_service.py:109-132`）对
白名单外的 `resources.executor` 值无条件 `return True`，节点被标 `dispatched` 却永不投递
任何 Celery 任务，run 永不终结，无告警。

**实现**（`src/omichub/application/services/mas_scheduler_service.py`）：

- 在 6 个已知 executor 分支之后补 `else` 分支，调用新增的 `_fail_unknown_executor` 方法。
- `_fail_unknown_executor`：重新拉取最新节点（避免版本号不一致），做 `DISPATCHED → FAILED`
  转换，记录 `A2AEventType.NODE_FAILED` 事件（带 `error_code=UNKNOWN_EXECUTOR` 的 summary），
  并将 run 状态推进到 `failed`——与 worker 侧失败语义完全一致，run 可正常终结。
- 新增 `EventSummary` 到导入列表。

**测试**（`tests/unit/domain/mas/test_scheduler.py`）：

- 更新 `test_scheduler_dispatches_a_ready_node_once`：改用 `resources={"executor":"fake"}` +
  monkeypatch `enqueue_task`（原测试用 `resources={}` 实际上是在回归悬挂 bug）。
- 新增 `test_scheduler_fails_node_with_unknown_executor`：验证未知 executor 时节点 → `failed`、
  run → `failed`、事件序列 = `[NODE_DISPATCHED, NODE_FAILED]`、`error_code=UNKNOWN_EXECUTOR`、
  无 Celery 任务投递。
- 同步更新陈旧的 `test_agent_capabilities.py`：旧期望值未反映 `deseq2`（rnaseq flow）和
  scrna executor 的自动派生，改为断言子集关系。

验收：`uv run pytest tests/unit/domain/mas/ -q` → **40 passed**。

---

### 15.2 ✅ 已完成：阶段 A — fan-out 接入超频群聊泳道 UI（纯前端）

**问题**：后端已在 `chat_service.py:5602/5646` 发 `type="subagents"` SSE chunk（started /
aggregated），前端 `useAgentChatStream.ts` 没有对应 `case`，事件被丢弃；用户看不到"哪几个
专家在并行、各自进度"。

**实现**：

1. **`frontend/src/components/ai-chat/types.ts`**  
   `OverdriveProgress` 接口新增 `readonly?: boolean`（用于区分 fan-out 卡片与真实超频控制台，
   隐藏暂停/终止/指令条）。

2. **`frontend/src/components/ai-chat/OverdriveProgressCard.vue`**  
   控制条 `v-if` 增加 `!progress.readonly` 条件——fan-out 泳道卡片不显示超频专属控制 UI。

3. **`frontend/src/composables/useAgentChatStream.ts`**  
   - 新增 `SubagentFanoutEvent` 接口（导出）：`{ phase, toolCallId, tasks[], success?, summary? }`。
   - `AgentStreamCallbacks` 新增 `onSubagentFanout?` 回调。
   - 新增 `case 'subagents'`：
     - started → 解析 `tasks[{index,agent_id,task}]`，标 `status:'running'`；
     - aggregated → 解析 `progress[{index,agent_id,status,elapsed_s}]`，映射终态；
     - 回调 `cb.onSubagentFanout?.(event)`。

4. **`frontend/src/stores/agentHub.ts`**  
   `streamChat` 回调集新增 `onSubagentFanout`：
   - started 阶段：若不存在以 `fanout-{toolCallId}` 为 id 的消息，新建一条 `role:'system'` 消息，
     `overdriveProgress.tasks` 映射自 fan-out tasks，`readonly: true`。
   - aggregated 阶段：找到同 id 消息，更新 task 终态、`phase:'completed'`、`label`、`completed`。
   - 字段适配：`index → taskId`、`agent_id → agentId`、`status` 直传、fan-out 无 `errorSummary`。

**复用关系**：完全复用 `OverdriveProgressCard.vue` 的现有 `tasks[]` 泳道渲染，无新增组件。
前端架构不变，只加了事件解析路径和 store 处理逻辑。

验收：`npx vue-tsc --noEmit` → **exit 0，0 errors**。

---

### 15.3 🔲 待实现：阶段 B — 打通 fan-out 的 ask_user 冒泡（后端）

**当前缺口**：子专家在并行执行中调 `ask_user` 时，`parallel_subagent_service.py:496` 把该
子任务标 `awaiting_input`，但对话内 fan-out 聚合路径（`chat_service.py` 约 5646 行）只发
`type="subagents"` chunk，不再发 `ask_request`——子专家的决策询问前端弹不出来。

**需要做的**（后端，改 `chat_service.py`）：

- 在 `chat_service.py:5646` 之后、发 `subagents.aggregated` 之前，检测
  `fanout_envelope.ui_payload.progress` 中是否存在 `status in {"awaiting_input",
  "approval_pending"}` 的子任务。
- 若命中，从 `fanout_envelope.llm_payload.results` 里提取对应子任务的 `user_request`
  字段（`parallel_subagent_service.py:130`），构造 `ask_request` chunk（复用
  `chat_service.py:5911/6549` 的既有格式）并额外 `yield`。
- 注意两条路径（legacy loop `~5900`、LangGraph `~6549`）都要改（见 [[langgraph-vs-legacy-dual-path]]）。
- 验收：开启 fan-out，让一个子专家需要 `ask_user`，前端弹 `AskUserCard`，答完后该子任务
  状态从 `awaiting_input` 变为 `succeeded`。

**需要变更的文件**：
- `src/omichub/application/services/chat_service.py`（两处，legacy + LangGraph）
- `tests/unit/test_parallel_subagent_service.py`（加负路径测试）

---

### 15.4 🔲 待实现：阶段 C — 把 AgentTeams Case 包装进超频房间（后端为主）

**目标**：让用户在超频群聊里看到 AgentTeams Case 的推进——"Manager 分派 → 角色领取工作项
→ 请求审批（用户在群里批准）→ 质控 → 交付"——而不是跳转到独立的 `/agent-teams/cases/:id` 页面。

**架构要点**（依赖 AgentTeams Bridge 部署才能端到端验证，见 §13.2）：

- **新增 `CaseRoomProjector`**（`src/omichub/application/services/case_room_projector.py`）：
  订阅 `AgentTeamsService.stream_case_events`，把 Case 审计事件翻译成超频 SSE chunk：
  - `case.created` → `room_speech`（Manager：确认分派 Case）
  - `work_item.assigned` → `room_speech`（对应角色，`senderAgent.role='worker'`）
    + `overdrive_progress`（泳道更新）
  - `approval.requested` → `overdrive_approval_request`（复用 `OverdriveApprovalCard.vue`）
  - `skill.finished` → `room_speech`（角色报告完成）
  - `quality.decision` → `room_speech`（Manager 汇报质量结论）
  - `case.closed` → `room_speech`（Manager 宣布关闭）+ `mode_changed` 退出超频
  - `senderAgent` 映射：`data-steward` → `agent-general`，`workflow-operator` → `agent-rnaseq`
    等（可配置，按 Case 的 `flow_id` 选对应领域专家）。
- **触发时机**：Case 建成（确认卡通过）后，超频房间自动 "订阅" 该 Case 的事件投影；
  `session.sandbox_meta` 里记录 `active_case_id`，`watch_cases` Celery 任务升级为投影驱动。
- **审批闭环**：`overdrive_approval_request` → 前端用户点批准 → 调现有
  `approve_and_submit_task`（`agentteams_service.py:244`）→ 继续推进。

**需要变更的文件**：
- 新建 `src/omichub/application/services/case_room_projector.py`
- `src/omichub/application/services/agentteams_case_tool_service.py`（建 Case 后注入 projector）
- `src/omichub/infrastructure/celery_app/tasks/agentteams.py`（`watch_cases` 升级为投影）
- `tests/unit/test_case_room_projector.py`（用 mock Case 事件流验证翻译映射）

**单测可独立完成**，不依赖 Bridge。端到端验收须 Bridge 部署开启。

---

### 15.5 🔲 待实现：阶段 D — 统一入口与可读性（前端体验）

优先级最低，可独立 PR。

1. **`OverdriveToggle` 语义升级**：文案改为"团队协作模式"，在 fan-out/Case 也有多专家参与
   时自动激活（不只是超频房间）。改动文件：`AgentSandbox.vue`、`StudioView.vue`。

2. **worker 发言默认展开**：`KimiMessageItem.vue` 里 `isWorkerSpeech` 折叠逻辑加 `defaultOpen`
   配置，让短回复（< 200 字）默认展开，长回复才折叠。

3. **handoff 过场卡片**：`useAgentChatStream.ts` 的 `case 'handoff'` 已解析 source/target/reason，
   在 store `onHandoff` 里插一条 `role:'system'` 消息显示"专家 A → 专家 B（原因：…）"，
   不依赖任何新组件。

---

### 15.6 验收清单（提 PR 前确认）

| 项 | 命令 | 期望 |
| --- | --- | --- |
| 后端相关单测 | `uv run pytest tests/unit/domain/mas/ tests/unit/test_agent_config_consistency.py -q` | 全通过 |
| 前端类型检查 | `cd frontend && npx vue-tsc --noEmit` | exit 0 |
| 配置一致性 | `uv run pytest tests/unit/test_agent_config_consistency.py -q` | 6 passed |
| 阶段 B 验收 | fan-out 里 ask_user 弹窗 | 手动 |
| 阶段 C 验收 | Bridge 部署后群聊看 Case 推进 | 手动（Bridge 开启后）|

