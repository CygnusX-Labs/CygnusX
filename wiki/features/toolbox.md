# L1 生信工具箱

L1 生信工具箱（`/tools`）提供可重复的单点生信操作与轻量可视化：差异表达、富集分析、BLAST、系统发育树、序列工具、参考基因组浏览等。它面向“明确工具 + 明确参数”的任务，不承担多步骤科研编排。

> **当前状态**：工具路由自动发现、双注册表、同步/异步任务、ToolBridge 五种调用模式和多个分析镜像已实现。各工具的实际可用性取决于配置、数据、Worker 与镜像；FASTQ QC、系统发育离线等仍有限制。

## 工具如何被注册

```text
src/cygnusx/tools/<snake_case_package>/
  router.py
      │
      ▼
register_tool_routers()（pkgutil 自动发现）
      │  三处命名映射：kebab-case key ↔ snake_case 子包 ↔ 物理目录
      ▼
/api/v1/tools/<tool-key>/*
```

新增工具子包无需修改总路由；但必须在两套注册表中声明，否则会出现“后端可用但前端不显示”或“AI 不知道有该工具”。

## 双注册表

| 注册表 | 作用 | 消费方 |
| --- | --- | --- |
| `tool_configs/tools_setting.yaml` | 工具卡片、分组、配色、页面入口 | L1 前端 |
| `tool_configs/tools_schema.yaml` | LLM function schema、调用模式、确认要求 | Agent/ToolBridge |

- 两套注册表**不会自动对齐**；靠 lint 与检索评测门禁发现漂移。
- 均支持 mtime 热重载。
- `tools_setting.yaml` 当前约 19 个工具、6 个分组；`tools_schema.yaml` 静态 45 个 LLM function，运行时另由 `FlowToolSchemaCompiler` 为每个 `ai.enabled` Flow 生成 `cygnusx_prepare_<slug>_submission` 动态工具（不写入该文件；`LEGACY_PIPELINE_TOOLS=false` 时停止注册）。数量以文件为准。
- 工具页面设计规范见 [`tool_configs/tools_design.md`](../../tool_configs/tools_design.md)。

## 任务模型

| 类型 | 存储 | 示例 |
| --- | --- | --- |
| 共享异步任务 | `tasks` 表，按 `flow_id` 区分 | DEG、KEGG 富集、GSEA、共线性 |
| 工具专属任务 | `blast_tasks` | BLAST |
| 同步/短任务 | 请求内完成 | 序列转换、简单统计 |
| 页面型工具 | 打开独立页面 | JBrowse、部分可视化 |

- 统一异步入队入口：`enqueue_task`；不要把新任务散落到自定义队列。
- Celery `include` / `task_routes` 是手工维护的；新增任务必须同步登记。
- 分析镜像示例：`cygnusx-r-enrichment:v1`、`cygnusx-r-deg:v1`、`cygnusx-synteny:v1`；镜像 tag 以 `deploy/image-mapping.yaml` 为准。

## ToolBridge 五种调用模式

| 模式 | 语义 |
| --- | --- |
| `backend_sync` | 请求内调用后端服务，直接返回 |
| `backend_shim` | 兼容旧工具/旧参数的薄适配 |
| `backend_async` | 创建独立作业（如系统发育树），不创建标准 Task |
| `open_page` | 返回前端页面入口 |
| `analysis_flow` | 进入标准 Flow 确认/提交链，创建 Task |

**分析中心 Flow 不走 `backend_async`**；它必须走 `analysis_flow`，以保证任务记录、目录、样本表、监控和计费一致。

`upload://file_id` 是工具输入的统一文件引用；不要直接接受任意宿主路径。

## 配置与数据

- 约 12 个 `*_config_yaml` 配置加载器，分别对应工具的参数、色板、参考数据等。
- 配置目录变更没有统一对账机制；改配置后需验证加载与页面显示。
- 参考基因组/JBrowse 使用独立 SQLite/FTS5 模块，见[参考基因组与数据库](reference-database)。
- 图形工具导出遵循 PNG/SVG DPI 与分组配色规范（见 `CygnusX_platform_design.md`）。

## 已知限制

| 限制 | 影响 |
| --- | --- |
| FASTQ QC 无独立 API | 只能通过 Flow/脚本路径，L1 页面不完整 |
| 系统发育树依赖离线/预置数据 | 不能假设在线数据库随时可用 |
| `YamlGenomeBrowser` 存在孤立实现 | 修改前先确认实际入口 |
| 配置目录无统一对账 | 配置漂移可能只在运行时发现 |
| ASYNC240 lint | 异步文件操作有静态检查告警，不是功能故障 |

## 新增工具清单

1. 在 `src/cygnusx/tools/` 新建 snake_case 子包与 `router.py`；
2. 在 `tools_setting.yaml` 添加卡片与分组；
3. 在 `tools_schema.yaml` 添加 LLM schema 与调用模式；
4. 如需异步：登记 `enqueue_task`、Celery include/task_routes、任务表与前端状态；
5. 如需镜像：更新 `image-mapping.yaml` 并完成 6 处同步；
6. 跑 lint、单测、工具页面手工验证与检索评测。

详细规范见[生信工具接入](../development/bio-tool-guide)。

## 关联文档

- 权威基线：[`CygnusX_toolbox_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_toolbox_architecture.md)、[`CygnusX_platform_design.md`](../../ARCHITECTURE_DESIGN/CygnusX_platform_design.md)
- [分析流程](workflows) · [生信工具接入](../development/bio-tool-guide) · [参考基因组与数据库](reference-database)
