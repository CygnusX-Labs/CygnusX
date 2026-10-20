# 功能特性

本章节介绍 CygnusX 面向终端用户的核心功能，包括 AI 助手、分析流程、生信工具箱、数据下载、
知识库、沙盒终端与参考数据。功能是否可用受模块注册、权限、Agent 配置和部署开关共同影响；
页面描述的是能力形态，不代表当前环境已完成运行验收。

## AI 与研究

- [AI 助手与工作台](ai-chat) — 四种执行形态、专家路由、知识检索、工具与技能
- [AI 多 Agent 协作](ai-collaboration) — Supervisor / Handoff / Map-Reduce / 协作室；Overdrive 为历史命名
- [科研数据与证据边界](../research/evidence-boundaries) — 已实现、已隔离测试、已运行验证的区别

## 分析与工具

- [分析流程与工作流](workflows) — YAML 声明式流程、双提交通道与新增流程方法
- [生信工具箱](toolbox) — 工具自动发现、双注册表、ToolBridge 五种执行模式
- [流程监控面板](workflow-monitor) — Snakemake 工作流实时监控
- [RNA-seq 分析](rna-seq) — RNA-seq 流程说明
- [ATAC-seq 分析](atac-seq) — ATAC-seq 流程说明
- [系统发育树构建](phylogenetic-tree) — 多序列比对与系统发育树工具

## 数据与知识

- [数据下载](downloads) — EBI/NCBI 公共数据库下载、云存储直拉与运行边界
- [数据发现与导入](../research/data-discovery) — 寻宝鼠、Dataset 导入与下载交接面
- [实验室知识库](knowledge-base) — Markdown 源内容、数据库版本与检索索引
- [参考基因组与数据库](reference-database) — JBrowse 2 基因组浏览器与参考数据

## 运行环境

- [云端沙盒终端](sandbox-terminal) — 浏览器交互式隔离容器终端
- [沙箱与工作台](../architecture/sandbox) — Chat 沙箱与 Studio 一会话一容器的差异

## 功能扩展入口

| 扩展类型 | 配置文件/位置 | 说明 |
|---|---|---|
| 新增分析流程 | `flows/*.yaml` | 声明式 YAML，热重载；契约变更需遵循 FlowFrame v2.0 |
| 新增生信工具 | `tool_configs/tools_setting.yaml`、`tools_schema.yaml` + `tool_configs/<tool>/` | 前端卡片、AI schema 与专属配置双注册 |
| 新增知识库文档 | `docs/knowledge/*.md` + `meta.yaml` 或 `wiki/` | 先更新源文档，再同步到数据库索引 |
| 新增参考基因组 | `tool_configs/jbrowse/jbrowse_config.yaml` | JBrowse 2 配置 |
| 新增 Agent | `data/ai/*.yaml` + `data/CygnusX.yaml` 的 `agents.enabled` | 两处同时登记，否则静默不加载 |

具体开发流程见[开发指南](../development/index)，子系统契约见[架构总览](../architecture/index)。
