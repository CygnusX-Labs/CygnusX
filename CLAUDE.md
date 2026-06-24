# CLAUDE.md - OmicHub 项目指南

## 项目概述

OmicHub 是华中农业大学园艺林学学院的私有化多组学分析平台。
采用 DDD（领域驱动设计）分层架构，技术栈：FastAPI + Vue 3 + PostgreSQL + Redis + Celery + Snakemake。

## 关键约束

- **1 人生信维护**：架构决策优先考虑运维简单性，拒绝过度工程
- **单服务器部署**：Docker Compose 单机部署，并发 < 20
- **私有化**：数据不出内网，AI API 可配置为 Kimi（国产）

## 项目结构

```
src/omichub/
├── api/v1/            # FastAPI 路由层（表示层）
├── application/       # 应用服务 + DTO（应用层）
├── domain/            # 六域：user/flow/task/file/ai/mcp（领域层）
├── infrastructure/    # 数据库/缓存/Celery/执行器（基础设施层）
├── core/              # 配置、安全、异常、日志
└── middleware/        # 认证、RBAC、限流
```

## 开发命令

- `make dev` — 启动后端开发服务器
- `make test` — 运行测试
- `make lint` / `make format` — 代码检查/格式化
- `make migrate` — 执行数据库迁移
- `make docker-up` — Docker Compose 启动

## 代码规范

- Python 3.11+，使用 ruff 格式化，行宽 100
- Pydantic v2 进行数据校验
- SQLAlchemy 2.0 异步 ORM
- 类型注解必须（mypy strict 模式）
