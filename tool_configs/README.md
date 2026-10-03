# 生信工具箱配置（tool_configs/）

本目录是**工具箱的集中配置根**，仿 `flows/` 仓库内源码管控。三类内容分治：

| 类型 | 文件 | 用途 |
|------|------|------|
| 前端注册表 | `tool_configs/tools_setting.yaml` | 「哪些工具加载到前端」+ 每张卡片展示元数据（title/description/icon/gradient/route/group/enabled/order/config_dir） |
| LLM 工具注册表 | `tool_configs/tools_schema.yaml` | AI 助手可调用的工具 function schema（name/description/input_schema/invocation_mode/双通道字段白名单） |
| 工具功能配置 | `<工具名>/*.yaml` | 该工具的后端运行参数（参考基因组、物种列表、镜像资源等） |

> 展示元数据（tools_setting）与 LLM schema（tools_schema）解耦：前者供前端工具箱卡片消费，后者供 Agent/ToolBridge 消费。同一工具要在两边分别登记（见下文「新增工具」）。
>
> 目录名使用 `tool_configs/` 而非 `tools/`，是为了与后端代码包 `src/cygnusx/tools/` 明确区分：
> 前者只放 YAML 配置与契约文档，后者放工具后端实现。

**命名映射规则**（三处命名刻意不同，新增工具按下表对齐）：

| 命名位置 | 风格 | 示例 |
|---|---|---|
| 前端路由 key / YAML key / API 路径 token | kebab-case | `fastq-qc`、`phylogenetic-tree` |
| 后端代码子包名 / Python import 路径 | snake_case | `cygnusx.tools.fastq_qc`、`cygnusx.tools.phylogenetic_tree` |
| `tool_configs/` 物理目录名 | 跟随后端子包（snake_case），个别历史目录为 kebab-case | `fastq_qc/`、`phylogenetic-tree/` |

## 目录结构

```
tool_configs/
├── tools_setting.yaml          # 前端注册表（前端 GET /api/v1/tools 消费）
├── tools_schema.yaml           # LLM 工具注册表（ToolBridge/MCP cygnusx-tools preset 消费）
├── evals/                      # 工具选择评测固定数据集与报告
├── blast/                      # BLAST：blast_config.yaml + blast_db.yaml（库注册）+ ARCHITECTURE.md
├── deg/                        # DEG：deg_config.yaml + scripts/ + examples/（引擎口径见其 README）
├── enrichments/                # GO/KEGG 富集：species_config.yaml + R 脚本 + KEGG_Docker_契约.md
├── fastq_qc/                   # FASTQ 质控：config.yaml + ARCHITECTURE.md
├── gsea/                       # GSEA：gsea_config.yaml + resources.yaml + examples/
├── jbrowse/                    # JBrowse：jbrowse_config.yaml（参考基因组/轨道）
├── phylogenetic-tree/          # 系统发育树：config.yaml + defaults.yaml（工具暂下线，配置保留）
├── synteny/                    # 共线性：synteny_config.yaml + synteny_runner.py（容器构建上下文）
├── terminal/                   # 云端终端：terminal_config.yaml + terminal_images.yaml + docker/（镜像构建上下文）
├── download/                   # EBIDownload：download_config.yaml
├── volcano/                    # 火山图示例数据（纯前端工具）
├── primer/、europe_pmc/、workflow_monitor/  # 契约说明与模板
└── tools_design.md             # 工具页面设计规范（权威文件，架构库已登记引用）
```

> 仅**有后端配置或契约文档**的工具才建子目录。纯前端 mock 工具（plot / venn-upset / wetlab-calculators 等）的展示信息统一在 `tools_setting.yaml`，不建目录。

## 后端入口

工具代码已按「模块化」收口到 `src/cygnusx/tools/` 包，每个工具自成子包（api/service/schema/config/tasks/runner）。路由由 `cygnusx.tools.register_tool_routers` **自动发现**挂载（`src/cygnusx/tools/__init__.py`），新增工具无需改 `api/v1/router.py`。

| 工具 | 代码子包 | API prefix | 配置项（`core/config.py`） |
|------|----------|-----------|---------------------------|
| 注册表 | `cygnusx.tools.registry` | `/api/v1/tools`（`GET /tools`、`POST /tools/reload`） | `tools_setting_yaml` |
| BLAST | `cygnusx.tools.blast` | `/api/v1/blast/*` | `blast_config_yaml` |
| DEG | `cygnusx.tools.deg` | `/api/v1/deg/*` | `deg_config_yaml` |
| 富集分析 | `cygnusx.tools.enrichments` | `/api/v1/enrichment/*` | `enrichment_config_yaml` |
| GSEA | `cygnusx.tools.gsea` | `/api/v1/gsea/*` | `gsea_config_yaml` |
| 共线性 | `cygnusx.tools.synteny` | `/api/v1/synteny/*` | `synteny_config_yaml` |
| JBrowse | `cygnusx.tools.jbrowse` | `/api/v1/jbrowse/*` | `jbrowse_config_yaml` |
| 系统发育树 | `cygnusx.tools.phylogenetic_tree` | `/api/v1/phylogenetic-tree/*`（工具暂下线，代码保留） | `phylogenetic_tree_config_yaml` + `phylogenetic_tree_defaults_yaml` |
| FASTQ 质控 | `cygnusx.tools.fastq_qc`（config/schema/runner 已建，**API 路由未建**，前端为参数预检态） | — | `fastq_qc_config_yaml` |
| 绘图 shim | `cygnusx.tools.shims`（volcano/manhattan，经 ToolBridge `backend_shim` 调用，无独立路由） | — | — |
| 纯配置工具 | `cygnusx.tools.download` / `cygnusx.tools.terminal`（仅 config 加载器） | — | `download_config_yaml` / `terminal_config_yaml` / `terminal_images_config_yaml` |

异步工具（BLAST/DEG/enrichments/GSEA/synteny）共用 `tasks` 表（`TaskModel`，按 `flow_id` 域隔离）、统一经 `enqueue_task` 投递（Celery/RocketMQ 双通道）；**新增 Celery 任务仍须在 `infrastructure/celery_app/celery.py` 的 `include` 与 `task_routes` 手动登记**，否则 worker unregistered。

各工具的配置加载器同模式：单例 + mtime 热重载，文件缺失/解析失败回退默认配置，绝不抛异常。

## 新增工具（模块化流程）

1. **建代码子包**：`src/cygnusx/tools/<工具名>/`，内含 `api.py`（声明 `router` + `prefix` + `tags`）及 `service.py`/`schema.py`/`config.py`/`tasks.py` 等；异步工具仿 BLAST 任务架构（见 `tools_design.md` §5.1.2）。
2. **登记前端展示**：在 `tool_configs/tools_setting.yaml` 的 `tools` 列表追加一项（key/title/description/icon/gradient/route/group/enabled/order/config_dir）。
3. **登记 LLM schema**（仅当 AI 助手可调用）：在 `tool_configs/tools_schema.yaml` 追加条目（name/description/input_schema/invocation_mode/llm_result_fields/ui_result_fields），遵守 §15.8 Description 工程规范；改后跑 `pytest tests/unit/tools/test_tool_schema_lint.py`。
4. **放功能配置**：仓库根 `tool_configs/<工具名>/` 下放 YAML，由子包内 `config.py` 加载器读取，并在 `core/config.py` 加 `xxx_config_yaml` 字段指向它。
5. **登记 Celery**（仅异步工具）：`infrastructure/celery_app/celery.py` 的 `include` 列表加 `cygnusx.tools.<工具名>.tasks`，`task_routes` 加队列映射。
6. **前端路由/图标**：`frontend/src/router/index.ts` 加 `tools/<key>` 子路由；若用新图标在 `ToolsHubView.vue` 的 `ICON_MAP` 登记。

> 第 1 步建好子包后，`register_tool_routers` 会自动发现并挂载其路由 —— **无需改 `api/v1/router.py`**。这是模块化的关键：工具代码自包含，核心路由表零侵入。但第 2/3 步两个注册表**不会自动对齐**，漏登记任何一边该工具就不可见（前端不可见 / Agent 不可调）。

## 改完如何生效

**改 YAML 文件即生效，无需重启**：加载器按文件 mtime 自动热重载。

- `tool_configs/tools_setting.yaml` 改完 → 前端刷新工具箱即可见（或调 `POST /api/v1/tools/reload` 强制）。
- 各工具 `*.yaml` → 对应子包 config 加载器按 mtime 热重载；已创建任务仍使用各自的输入快照。
- **改 Python 代码不热重载**：`omichub-web` 容器 `--workers 2` 无 reload，改后端代码须 `docker restart omichub-web`；改 Celery task 须 `docker restart omichub-worker`。

## 部署（重要）

`tool_configs/` 必须**对 web 容器可读**，否则三个加载器静默回退空配置（工具箱空白 / 无参考基因组 / 物种下拉空）：

- **开发**：`deploy/docker/docker-compose.yml` 已挂 `../../tool_configs:/app/tool_configs:ro`（与 `flows/` 同款）。
- **生产**：prod 不挂源码，`Dockerfile` 已 `COPY tool_configs/ ./tool_configs/` 打进镜像（与 `src/` 同款）。
- 改 `tool_configs/` 下文件，dev 经挂载即时可见；prod 需重建镜像。

## 架构文档归属

工具箱子系统的 as-built 全景见 `ARCHITECTURE_DESIN/CygnusX_toolbox_architecture.md`（后端框架、任务模型、ToolBridge 通道、注册表链路）；工具**页面**设计规范（布局/样式/交互）仍以本目录 `tools_design.md` 为唯一详细来源，`CygnusX_platform_design.md` §2.2 为其基线摘要。
