# 功能特性

本章节介绍 OmicHub 面向终端用户的核心功能，包括 AI 助手、分析流程、数据下载、知识库、沙盒终端与各类生信工具。

## 内容导航

- [AI 聊天助手](ai-chat) — Cherry Studio SSE 架构、助手系统与 Provider 配置
- [分析流程与工作流](workflows) — YAML 声明式流程与新增流程方法
- [数据下载](downloads) — EBI/NCBI 公共数据库下载与云存储直拉
- [实验室知识库](knowledge-base) — 基于 Markdown 的在线文档系统
- [云端沙盒终端](sandbox-terminal) — 浏览器交互式隔离容器终端
- [参考基因组与数据库](reference-database) — JBrowse 2 基因组浏览器与参考数据
- [系统发育树构建](phylogenetic-tree) — 多序列比对与系统发育树工具
- [流程监控面板](workflow-monitor) — Snakemake 工作流实时监控
- [RNA-seq 分析](rna-seq) — RNA-seq 流程说明
- [ATAC-seq 分析](atac-seq) — ATAC-seq 流程说明

## 功能扩展入口

| 扩展类型 | 配置文件/位置 | 说明 |
|---|---|---|
| 新增分析流程 | `flows/*.yaml` | 声明式 YAML，热重载 |
| 新增生信工具 | `tool_configs/tools_setting.yaml` + `tool_configs/<tool>/` | 注册表 + 专属配置 |
| 新增知识库文档 | `docs/knowledge/*.md` + `meta.yaml` | 纯 Markdown，在线编辑 |
| 新增参考基因组 | `tool_configs/jbrowse/jbrowse_config.yaml` | JBrowse 2 配置 |
