# OmicHub

私有化多组学分析平台 - 华中农业大学园艺林学学院

## 技术栈

- **后端**: FastAPI + SQLAlchemy 2.0 + PostgreSQL 14+ + Redis 7+ + Celery
- **前端**: Vue 3 + TypeScript + Vite + Naive UI + Pinia
- **流程引擎**: Snakemake 8.0+
- **AI**: MCP SDK + Kimi/OpenAI API
- **部署**: Docker Compose

## 快速开始

### 环境要求

- Python >= 3.11
- Node.js >= 18
- Docker >= 24.0
- uv (Python 包管理器)

### 安装

```bash
# 安装后端依赖
uv sync

# 安装前端依赖
cd frontend && npm install
```

### 开发

```bash
# 复制环境变量
cp .env.example .env

# 启动后端
make dev

# 启动前端 (另一个终端)
make frontend-dev
```

### Docker 部署

```bash
# 启动全部服务 (PostgreSQL + Redis + FastAPI + Celery + Nginx)
make docker-up

# 访问 http://localhost:8888
```

## 项目结构

```
src/omichub/          后端 Python 包 (DDD 分层)
  api/                表示层 - FastAPI 路由
  application/        应用层 - 用例编排
  domain/             领域层 - 六域 (用户/流程/任务/文件/AI/MCP)
  infrastructure/     基础设施层 - 数据库/缓存/队列/执行器
  core/               核心配置
  middleware/         中间件
frontend/             前端 Vue 3
tests/                测试
deploy/docker/        Docker 部署配置
docs/                 架构设计文档
```

## 文档

详细架构设计见 `docs/` 目录。
