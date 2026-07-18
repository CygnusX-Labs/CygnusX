# 架构与设计文档索引

本目录集中存放 OmicHub 的项目级架构、设计规范和实施方案。修改相关功能前，请先阅读对应文档，确保实现与既有约束保持一致。

| 文件 | 内容说明 |
| --- | --- |
| `LOG_ARCHITECTURE.md` | 统一日志架构说明，定义应用、Celery、Nginx、Snakemake 与审计日志的目录、格式、挂载和容量保护策略。 |
| `omichub_design.md` | 项目级模块设计与接入指南，规定平台功能、分析流程、AI/Agent、异步任务及外部服务集成的分层与契约基线。 |
| `omichub_studio.md` | OmicStudio AI 分析工作台的实施进度与交接文档，记录沙盒、Agent、API、前端、验证状态、运维注意事项和待办事项。 |
| `fontend.md` | 前端视觉与交互规范，涵盖设计令牌、页面层级、组件状态、动效、响应式设计和可访问性要求。 |
| `plan_ai.md` | 多智能体编排、共享工作区与 A2A 架构实施方案，说明目标架构、状态管理、数据模型、事件协议和落地路径。 |
| `worker_images_plan.md` | Worker 轻量镜像与 Workspace 动态安装计划，定义 Worker 镜像边界、运行时挂载、Conda 环境缓存及实施步骤。 |

