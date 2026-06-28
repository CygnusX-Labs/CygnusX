# OmicHub

私有化多组学分析平台 - 华中农业大学园艺林学学院

## 技术栈

- **后端**: FastAPI + SQLAlchemy 2.0 + PostgreSQL 14+ + Redis 7+ + Celery
- **前端**: Vue 3 + TypeScript + Vite + Naive UI + Pinia
- **流程引擎**: Snakemake 8.0+
- **AI**: Cherry Studio SSE 架构 + Kimi/OpenAI API + MCP SDK
- **部署**: Docker Compose

## 快速开始

### 环境要求

- Python >= 3.11
- Node.js >= 18
- Docker >= 24.0
- uv (Python 包管理器)

### 本地开发

```bash
# 1. 复制环境变量
cp .env.example .env
# 编辑 .env，设置 JWT_SECRET_KEY、AL_API_KEY 等

# 2. 安装后端依赖
uv sync

# 3. 安装前端依赖
cd frontend && npm install

# 4. 启动 PostgreSQL + Redis（Docker）
make docker-up

# 5. 执行数据库迁移
make migrate

# 6. 初始化管理员账号
make init-admin

# 7. 初始化饼干定价策略（可选）
make init-cookies

# 8. 启动后端开发服务器
make dev

# 9. 启动前端开发服务器（另一个终端）
make frontend-dev
```

访问 http://localhost:5173（前端）或 http://localhost:8000/docs（API 文档）

### Docker 部署（推荐）

```bash
# 1. 复制并编辑环境变量
cp .env.example .env
# 必须修改：
#   - JWT_SECRET_KEY（随机长字符串）
#   - AL_API_KEY（阿里云 DashScope API Key）
#   - OMICHBUB_INIT_ADMIN_PASSWORD（生产环境必填）
#   - AI_CONFIG_ENCRYPTION_KEY（固定值，用于加密 API Key）

# 2. 构建前端
cd frontend && npm install && npm run build && cd ..

# 3. 启动全部服务（PostgreSQL + Redis + FastAPI + Celery + Nginx）
make docker-up

# 4. 执行数据库迁移
docker exec omichub-web uv run alembic upgrade head

# 5. 初始化管理员账号
docker exec omichub-web uv run python scripts/init_admin.py

# 6. 初始化饼干定价策略（可选）
docker exec omichub-web uv run python scripts/init_cookies.py

# 7. 访问
# 开发环境: http://localhost:8888
```

### 生产环境部署

```bash
# 使用生产环境 override（4 worker + 不暴露 DB 端口 + SSL）
docker compose -f deploy/docker/docker-compose.yml \
               -f deploy/docker/docker-compose.prod.yml up -d
```

生产环境注意事项：
- 设置 `APP_ENV=production`、`APP_DEBUG=false`
- 必须设置 `OMICHBUB_INIT_ADMIN_PASSWORD` 强密码
- `AI_CONFIG_ENCRYPTION_KEY` 必须为固定值（首次部署后不可更改，否则已加密的 API Key 无法解密）
- 配置 SSL 证书（挂载到 nginx）
- 不暴露数据库端口（prod.yml 已禁用）

## 配置说明

### AI Provider 配置

支持两种方式（可共存，方式 1 优先）：

**方式 1（推荐）：外置 YAML**

编辑 `data/ai_providers.yaml`，支持 `${ENV_VAR}` 插值引用 `.env` 中的密钥：

```yaml
providers:
  - name: aliyun
    provider_type: openai_compatible
    model: qwen3.7-max
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${AL_API_KEY}
    is_default: true
```

**方式 2：环境变量兜底**

仅在数据库无 Provider 时生效，在 `.env` 中设置 `KIMI_API_KEY` / `OPENAI_API_KEY`。

### AI 助手架构

采用 Cherry Studio SSE 架构（`docs/OmicHub_CherryStudio_整合实施文档.md`）：

- **SSE 流式聊天**: `POST /api/v1/chat/stream` — 逐 token 推送，支持推理过程
- **三层数据模型**: `chat_sessions`（会话）→ `chat_messages`（消息）→ `chat_assistants`（助手）
- **Provider 管理**: `ProviderManager` 单例 + `OpenAICompatibleProvider`（httpx 直连 SSE）
- **助手系统**: 6 个内置助手（通用/RNA-seq/单细胞/代码/文献/可视化）+ 自定义助手
- **技能注入**: 管理员可配置技能（Skill），激活后自动注入到 system prompt

## 临时文件清理

### 前端临时文件

```bash
# 清理前端构建缓存和产物
cd frontend
rm -rf node_modules dist .vite
npm install && npm run build

# 清理 npm 缓存（可选）
npm cache clean --force
```

### 后端 Python 缓存

```bash
# 清理 __pycache__、.pyc、缓存目录
make clean

# 或手动清理
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
```

### Docker 数据清理

```bash
# 停止并删除容器（保留数据卷）
make docker-down

# 停止并删除容器 + 删除数据卷（⚠️ 会丢失数据库和文件数据）
docker compose -f deploy/docker/docker-compose.yml down -v

# 清理 Docker 构建缓存和悬挂镜像
docker builder prune -f
docker image prune -f

# 彻底清理所有 OmicHub 相关资源（⚠️ 不可恢复）
docker compose -f deploy/docker/docker-compose.yml down -v --rmi all
docker volume rm $(docker volume ls -q | grep omichub) 2>/dev/null
```

### 数据库重置

```bash
# 方式 1：回滚最后一个迁移再重新执行
docker exec omichub-web uv run alembic downgrade -1
docker exec omichub-web uv run alembic upgrade head

# 方式 2：重置到指定版本
docker exec omichub-web uv run alembic stamp <revision_id>
docker exec omichub-web uv run alembic upgrade head

# 方式 3：彻底重建（⚠️ 删除所有数据）
docker compose -f deploy/docker/docker-compose.yml down -v
docker volume create --name deploy_pg_data 2>/dev/null; true
make docker-up
docker exec omichub-web uv run alembic upgrade head
docker exec omichub-web uv run python scripts/init_admin.py
```

### AI 聊天会话清理

```bash
# 清空所有聊天会话和消息（保留助手配置）
docker exec omichub-db psql -U omichub -d omichub -c "
  DELETE FROM chat_messages;
  DELETE FROM chat_sessions;
  DELETE FROM ai_messages;
  DELETE FROM ai_conversations;
"

# 清空测试技能
docker exec omichub-db psql -U omichub -d omichub -c "
  DELETE FROM skills WHERE is_builtin = false;
"
```

## 项目结构

```
src/omichub/          后端 Python 包 (DDD 分层)
  api/                表示层 - FastAPI 路由
    v1/               API v1 路由
      admin/          管理员路由 (skills/assistants/cookies/users)
  application/        应用层 - 用例编排
    services/         应用服务 (ai_service/chat_service/skill_service/...)
    schemas/          Pydantic DTO
  domain/             领域层 - 七域 (user/flow/task/file/ai/mcp/skill)
  infrastructure/     基础设施层
    ai_provider/      LLM Provider (litellm/kimi/openai_compatible)
    database/         SQLAlchemy ORM + 仓储实现
  core/               核心配置 (config/security/exceptions/logging)
  middleware/         中间件 (auth/rbac/cookie/rate_limit)
frontend/             前端 Vue 3
  src/
    components/       组件 (ai-chat/ admin/ sandbox/)
    composables/      组合式函数 (useChatStream/useAIWebSocket/...)
    stores/           Pinia 状态 (chatSession/chatAssistant/ai/auth/...)
    views/            页面
deploy/docker/        Docker 部署配置
  docker-compose.yml  开发环境
  docker-compose.prod.yml  生产环境 override
flows/                Snakemake 流程 YAML (rna_seq/atac_seq)
data/                 AI Provider YAML 配置
docs/                 架构设计文档
```

## 常用命令

| 命令 | 说明 |
|------|------|
| `make dev` | 启动后端开发服务器 |
| `make frontend-dev` | 启动前端开发服务器 |
| `make test` | 运行测试 |
| `make lint` | 代码检查 (ruff) |
| `make format` | 代码格式化 |
| `make migrate` | 执行数据库迁移 |
| `make migrate-new m="名称"` | 创建新迁移 |
| `make docker-up` | Docker Compose 启动 |
| `make docker-down` | Docker Compose 停止 |
| `make init-admin` | 初始化管理员账号 |
| `make init-cookies` | 初始化饼干定价策略 |
| `make clean` | 清理 Python 缓存文件 |

## 文档

详细架构设计见 `docs/` 目录：

- `OmicHub_CherryStudio_整合实施文档.md` — AI 助手 Cherry Studio SSE 架构
- `OmicHub_完整系统架构设计文档_v3.md` — 整体架构设计
- `modules/` — 各模块详细设计
