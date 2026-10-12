# 架构与数据

本章节介绍 CygnusX 当前实现的整体架构、数据目录布局和日志体系。架构边界、验证门禁和各专项 as-built 文档见 [`ARCHITECTURE_DESIGN/README.md`](../../ARCHITECTURE_DESIGN/README.md)。

## 内容导航

- [系统架构总览](overview) — 技术栈、DDD 分层、核心领域与数据流
- [数据目录结构](data-directory) — `/data/cygnusx` 目录布局与挂载说明
- [日志架构与排障](logging) — 统一日志目录、各服务写入方式、容量保护与排障

## 阅读边界

Wiki 用于操作和概念导航；涉及数据库表、Agent 执行路径、MCP、Skill、沙盒 capability、存储协议或镜像映射时，必须回到对应的 `ARCHITECTURE_DESIGN/CygnusX_*.md` as-built 文档和当前代码核对。

## 设计关键词

- **前后端分离**：Vue 3 + FastAPI，Nginx 作为入口与静态资源代理。
- **DDD 分层**：`api/` → `application/` → `domain/` → `infrastructure/`。
- **控制面与计算面分离**：主栈运行 Web / DB / Redis / Nginx / Beat / Flower；Worker 栈独立运行计算任务。
- **声明式流程**：`flows/*.yaml` + `GenericFlowBuilder` 支持新增流程无需改后端代码。
- **配置外置**：可运营配置进 `tool_configs/` 或数据库；密钥进环境变量。
