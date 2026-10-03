# CygnusX 生信工具箱子系统架构（as-built）

> **定位**：本文档是生信工具箱（L1 用户入口，`/tools`）的**后端框架与跨链路 as-built 全景**，覆盖代码框架、双注册表、任务模型、Agent 调用通道与部署契约。工具**页面**的布局/样式/交互规范不在本文重复，唯一详细来源是 `tool_configs/tools_design.md`（22 章规范，架构库"相关文档"已登记）；模块设计六原则中的工具基线摘要在 `CygnusX_platform_design.md` §2.2。
>
> 基线日期：2026-10-03。本文描述的是当日仓库实测状态（注册表加载、Celery 登记、lint 测试均实跑核验）。

---

## 0. 一页结论

工具箱 = **一个自动发现的代码框架 + 两份解耦的注册表 + 一张共享任务表 + 一条 Agent 调用通道**：

1. **代码框架**：`src/cygnusx/tools/` 下每个工具自成子包（api/service/schema/config/tasks/runner），`register_tool_routers`（`tools/__init__.py:55`）用 `pkgutil` 扫描子包的 `api` 模块自动挂载路由——新增工具零侵入 `api/v1/router.py`。
2. **双注册表解耦**：`tools_setting.yaml`（前端卡片，19 个启用工具）与 `tools_schema.yaml`（LLM function，43+ 条目含动态 Flow 工具）各自独立登记，**不会自动对齐**，漏任何一边该工具就不可见（前端不可见 / Agent 不可调）。
3. **任务模型**：DEG/enrichments/GSEA/synteny 四个异步工具复用共享 `tasks` 表（`TaskModel`，按 `flow_id` 域隔离）；BLAST 因缓存/命中统计等专属字段使用独立 `blast_tasks` 表。
4. **Agent 通道**：`ToolBridgeService` 按 5 种 `invocation_mode` 分发（backend_sync / backend_shim / backend_async / open_page / analysis_flow），结果走 `llm_payload`/`ui_payload` 双通道。

## 1. 代码框架：子包自动发现

```
src/cygnusx/tools/
├── __init__.py          # register_tool_routers：pkgutil 扫描 + include_router
├── registry/            # 工具箱注册表 API（GET /tools、POST /tools/reload）
├── blast/               # api config core schema service tasks cache events yaml_sync（10 文件，最全样板）
├── deg/                 # api config runner schema service tasks
├── enrichments/         # api config runner schema service tasks（GSEA runner 复用其 Docker 基类）
├── gsea/                # api config runner schema service tasks
├── synteny/             # api config runner schema service tasks
├── jbrowse/             # api config schema service tasks
├── phylogenetic_tree/   # api config core runner schema service tasks（工具暂下线，代码保留）
├── fastq_qc/            # config schema runner（API 路由未建，前端为参数预检态）
├── terminal/ download/  # 纯配置加载器（无 api 模块，自动发现跳过）
└── shims/               # volcano / manhattan 轻量绘图（经 ToolBridge backend_shim 调用，无路由）
```

**自动发现约定**（`tools/__init__.py` 模块 docstring 即契约）：子包有 `api` 模块且带 `router` 属性即挂载；`prefix`/`tags` 缺省按子包名推导；无 `api` 模块（纯配置工具）静默跳过。当前自动挂载 8 个子包路由（registry/blast/deg/enrichments/gsea/synteny/jbrowse/phylogenetic-tree）。

**命名映射**（三处刻意不同）：

| 位置 | 风格 | 例 |
|---|---|---|
| YAML key / 前端路由 token | kebab-case | `fastq-qc` |
| Python | snake_case | `cygnusx.tools.fastq_qc` |
| `tool_configs/` 物理目录 | 跟随后端子包，个别历史为 kebab | `fastq_qc/`、`phylogenetic-tree/` |

## 2. 双注册表与配置体系

### 2.1 tools_setting.yaml（前端注册表）

19 个启用工具，6 分组（sequence/visualization/analysis/genome/function/environment）+ 前端兜底"其他工具"。链路：

```
tool_configs/tools_setting.yaml
  → tools/registry/config.py::ToolItem（Pydantic）
  → tools/registry/schema.py::ToolItemDTO
  → GET /api/v1/tools（仅 enabled=true，按 order 升序）
  → frontend/src/types/tools.ts::ToolItem
  → ToolsHubView.vue（GROUP_MAP 分组渲染 + ICON_MAP 图标映射 + localStorage 折叠记忆）
```

`config_dir` 为**纯展示字段**（文档性，前端可跳转配置目录），当前无存在性对账校验；统一带 `tool_configs/` 前缀。

### 2.2 tools_schema.yaml（LLM 注册表）

静态 43 条 + 动态 Flow 编译工具（`schema_loader._load_flow_tools()` 从启用 `ai.enabled=True` 的 Flow 生成，`invocation_mode=analysis_flow`）。静态条目分布：backend_sync 25 / open_page 14 / backend_async 3 / backend_shim 2。

- **命名**：`cygnusx_` 前缀；Agent 控制流与协作室工具（transfer_to_agent / parallel_subagents / skill_route / agentteams-* / memory 系）豁免前缀，不参与 toolbox lint。
- **质量门禁**：`tests/unit/tools/test_tool_schema_lint.py` 强制 `TOOLBOX_PREFIX + TOOLBOX_CATEGORIES` 交集条目的描述四成分（80–300 字符、动词开头、"适用于"、边界句、"输入"）、keywords 非空、禁营销词、名称唯一。改 schema 必跑。
- **检索化注入**：`tool_selection.mode: full|retrieval`；工具数 >15 时可按 name+description+keywords 召回 Top-N（jieba 分词，异常回落 full）。评测基线 `tool_configs/evals/`（29 条固定用例，full/retrieval 双模式 86.21%，2026-10-03 实跑）。

### 2.3 配置加载器范式（全工具统一）

单例 ConfigManager + mtime 热重载 + 失败回退内置默认（绝不抛异常）。每份 YAML 对应 `core/config.py` 的 `*_config_yaml` Settings 字段：

| 工具 | Settings 字段 | YAML |
|---|---|---|
| 注册表 | `tools_setting_yaml` | `tools_setting.yaml` |
| LLM schema | `tools_schema_yaml` | `tools_schema.yaml` |
| BLAST | `blast_config_yaml` | `blast/blast_config.yaml` |
| DEG | `deg_config_yaml` | `deg/deg_config.yaml` |
| 富集 | `enrichment_config_yaml` | `enrichments/species_config.yaml` |
| GSEA | `gsea_config_yaml` | `gsea/gsea_config.yaml` |
| 共线性 | `synteny_config_yaml` | `synteny/synteny_config.yaml` |
| JBrowse | `jbrowse_config_yaml` | `jbrowse/jbrowse_config.yaml` |
| 系统发育 | `phylogenetic_tree_config_yaml` + `phylogenetic_tree_defaults_yaml` | `phylogenetic-tree/*.yaml` |
| FASTQ QC | `fastq_qc_config_yaml` | `fastq_qc/config.yaml` |
| 终端 | `terminal_config_yaml` + `terminal_images_config_yaml` | `terminal/*.yaml` |
| 下载 | `download_config_yaml` | `download/download_config.yaml` |

**部署契约**：`tool_configs/` 必须对 web 容器可读（dev bind-mount `:ro` / prod `COPY` 进镜像），否则加载器静默回退空配置（工具箱空白/物种下拉空）。

## 3. 异步任务体系

### 3.1 任务模型：一共享表 + 一专属表

| 工具 | 任务表 | 域隔离方式 |
|---|---|---|
| DEG / enrichments / GSEA / synteny | `tasks`（共享 `TaskModel`） | `flow_id` = `deg` / `kegg-enrichment` / `gsea` / `synteny` |
| BLAST | `blast_tasks`（`BlastTaskModel`） | 独立表，带 result 缓存、hit_count、identity/evalue 等专属字段 |

共享表工具的查询/归属校验模式一致：`select(TaskModel).where(id, user_id, flow_id)`（见 `deg/service.py:325`、`gsea/service.py:77`、`synteny/service.py:73`、`enrichments/service.py:207`）。

### 3.2 任务投递：enqueue_task 统一分发

`infrastructure/task_queue/dispatcher.py::enqueue_task` 是唯一投递入口，按 `task_queue_backend`（celery/rocketmq/hybrid）分流。工具任务全部经它投递，不直接 `apply_async`。

### 3.3 Celery 登记（手动，易漏）

`infrastructure/celery_app/celery.py` 的 `include` + `task_routes` **须手动登记**新工具的 tasks 模块，否则 worker unregistered。当前登记：

| 任务模块 | 队列 |
|---|---|
| `cygnusx.tools.jbrowse.tasks` | analysis |
| `cygnusx.tools.phylogenetic_tree.tasks` | phylo_tree（专用 Worker，已停建） |
| `cygnusx.tools.blast.tasks` | blast_search / blast_db_build（双队列拆分） |
| `cygnusx.tools.enrichments.tasks` | analysis |
| `cygnusx.tools.deg.tasks` | analysis |
| `cygnusx.tools.synteny.tasks` | analysis |

（GSEA 复用 enrichments 的 include 条目链，`gsea.tasks` 经 `enrichments.config` 间接登记——见 `gsea/tasks.py` 的 shared_task 注册。）

### 3.4 分析容器体系

异步工具在 Worker 内启动分析容器执行（Web 进程无 Docker CLI/Socket）。镜像契约：

| 镜像 | Dockerfile | 构建上下文 | Make 入口 |
|---|---|---|---|
| `cygnusx-r-enrichment:v1` | `deploy/docker/Dockerfile.enrichment` | `tool_configs/enrichments/` | `make docker-build-enrichment` |
| `cygnusx-r-deg:v1` | `deploy/docker/Dockerfile.deg` | `tool_configs/deg/` | `make docker-build-deg` |
| `cygnusx-synteny:v1` | `deploy/docker/Dockerfile.synteny` | `tool_configs/synteny/` | `make docker-build-synteny` |
| 终端镜像族 | `tool_configs/terminal/docker/`（存量豁免位） | 同目录 | `make docker-build-sandboxes` |

Dockerfile 归属规范：统一放 `deploy/docker/Dockerfile.<purpose>`；`tool_configs/terminal/docker/` 为登记过的历史存量豁免（详见 `tools_design.md` §5.1.2 存量豁免注记与 `deploy/docker/README.md` 镜像清单）。Worker 的 Docker Socket GID 约定见 `tools_design.md` §5.1.2（`scripts/worker-compose.sh` 动态读取，禁写死）。

### 3.5 结果目录协议

用户可见目录一律走 `StoragePathFactory.create_project_run_dir()`（`Protocol/file_protocol.md` v1.3）：`{data_mount}/users/{user_id}/{project_slug}/{tool}/{...}`；project_slug 由 `project_slug()` 安全目录名转换。BLAST 数据库另有 `blast_db_dir()` 特例。

## 4. Agent 调用通道（ToolBridge）

`application/services/tool_bridge_service.py` 是 AI 助手调用工具的唯一进程内通道（禁止 HTTP 自调用）：

```
LLM function call（OpenAI 规范）
  → MCPClient.call_tool（cygnusx-tools preset，从 tools_schema.yaml 动态构建）
  → ToolBridgeService.execute
      ├─ 参数校验 + upload://file_id 引用解析（chat-uploads 目录）
      ├─ _dispatch 按 invocation_mode 分发：
      │    backend_sync   → 进程内调 schema.service.method（可带 extra.celery_service 提交 Celery）
      │    backend_shim   → 进程内调轻量 shim（volcano/manhattan，纯前端级绘图逻辑）
      │    backend_async  → 默认 ARQ（arq_jobs.run_tool_async）；extra.celery_service=true 走 service
      │    open_page      → 返回 route 引导用户去工具页
      │    analysis_flow  → AnalysisFlowToolService（动态 Flow 工具，execute 顶层处理）
      └─ _package 双通道封装：
           llm_payload（≤3KB 摘要回灌 LLM）+ ui_payload（plotly_figure/table_data/confirm_card/
           task_id+progress_url 等透传前端渲染）
```

前端消费：SSE `tool_call`/`tool_result` 事件（`useAgentChatStream.ts`）→ 工具卡片（`McpToolCallCard.vue` 等 ai-chat 组件）识别 ui_payload 字段出图/出表/进度卡。

`upload://file_id` 协议：聊天上传文件存 `{data_root}/users/{uid}/workspace/chat-uploads/`，参数 description 须声明支持；大文件禁止内联塞参数。

## 5. 与其他子系统的边界

| 子系统 | 交界 | 权威文档 |
|---|---|---|
| MCP | cygnusx-tools preset 动态构建、MCP 调用判定/熔断/failure_kind | `CygnusX_mcp_architecture.md` §1.3 |
| Agent 执行 | ToolBridge 在两条 Chat Runtime（LangGraph/Legacy）中的位置、工具事件落库 | `CygnusX_agent_execution_framework.md` |
| AI 助手工具契约 | tools_schema 字段语义、检索注入、评测基线 | `tools_design.md` §15 |
| 模块门禁 | MODULE_LOCKED.yaml + 前后端双消费（工具箱在三段透传链末端） | `CygnusX_platform_design.md` §1 |
| Worker 镜像 | 通用 Worker 边界（Snakemake/Micromamba，不含分析容器） | `CygnusX_worker_images_plan.md`（提案） |
| 数据库 | tasks/blast_tasks 表、schema 对账 | `CygnusX_database_architecture.md` |
| 前端 | BioTools 视图、ToolsHub、PageHeader/ToolActionBar 共享组件 | `tools_design.md` §六–§十九 |

## 6. 修改验证矩阵（工具域专用）

| 改动 | 最小验证 |
|---|---|
| 任何 `tools_schema.yaml` 条目 | `uv run pytest tests/unit/tools/test_tool_schema_lint.py` + `scripts/tool_selection_eval.py --mode full\|retrieval` |
| 新增异步工具 | `make lint && make type-check` + Celery include/task_routes 登记 + 镜像 `make docker-build-<tool>` + 重启 worker 栈（`scripts/worker-compose.sh`） |
| 配置 YAML | 加载器实跑验证（`get_xxx_config()` 打印字段）+ mtime 热重载确认 |
| 前端工具页 | `npm run type-check && npm test`；动路由/布局再加 `npm run build` |
| 改后端 Python | `docker restart omichub-web`（无 reload）；改 task 代码 `docker restart omichub-worker` |

## 7. 已知缺口（2026-10-03 快照）

1. `config_dir` 为纯展示字段，无目录存在性对账（孤儿 YAML/目录靠人工发现——gsea/synteny 加载器缺失问题即由此产生，已补齐）。
2. FASTQ QC 前端为参数预检态（"任务创建 API 正在接入"），后端 config/schema/runner 已建但无 api 路由。
3. 系统发育树工具暂下线（schema 条目注释、tools_setting enabled=false、phylo-worker 停建）；evals 已移除对应 4 条用例，恢复时须同步还原。
4. 前端存在孤儿视图 `YamlGenomeBrowser.vue`（无路由引用、未注册）。
5. ASYNC240 等 lint 存量问题散在 gsea/synteny 的 api.py/tasks.py（pathlib 同步 IO 于 async 函数）。
