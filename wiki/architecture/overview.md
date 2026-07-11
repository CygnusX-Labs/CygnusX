# 系统架构总览

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Naive UI + Pinia |
| 后端 | FastAPI + Pydantic v2 + SQLAlchemy 2.0 |
| 数据库 | PostgreSQL 14+ |
| 缓存/队列 | Redis 7+ + Celery |
| 流程引擎 | Snakemake 8.0+ |
| AI | Cherry Studio SSE + Kimi/OpenAI API + MCP SDK |
| 部署 | Docker Compose（主栈 + Worker 栈） |

## DDD 分层

```text
Browser (Vue 3)
  ↓ HTTPS/WebSocket
Nginx
  ↓ /api/*
FastAPI (/api/v1)
  ├─ api/v1/          路由
  ├─ application/     应用服务 + DTO
  ├─ domain/          领域模型
  └─ infrastructure/  数据库/缓存/外部服务
PostgreSQL / Redis / Celery / Snakemake / Docker
```

## 核心领域

| 领域 | 聚合根 | 说明 |
|---|---|---|
| 用户域 | `User` | 注册、登录、角色、工作空间隔离 |
| 流程域 | `FlowDefinition` | YAML 流程定义、参数模式 |
| 任务域 | `Task` | 生命周期、状态机、日志 |
| 文件域 | `Sample` | 样本、数据文件、结果归档 |
| AI 域 | `Conversation` | 会话、消息、上下文窗口 |
| MCP 域 | `MCPServer` | MCP Server 注册、工具发现 |

## 关键数据流

- **用户请求流**：Browser → Nginx → FastAPI → Service → Domain → PostgreSQL
- **异步任务流**：FastAPI → Redis → Celery → Snakemake → 共享存储
- **AI 对话流**：Browser ↔ FastAPI WebSocket ↔ AI Service ↔ Kimi/OpenAI API
- **任务监控流**：Celery → Redis Pub/Sub → WebSocket → Browser
