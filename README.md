# OmicHub

私有化多组学分析平台 - 华中农业大学园艺林学学院

## 技术栈

- **后端**: FastAPI + SQLAlchemy 2.0 + PostgreSQL 14+ + Redis 7+ + Celery
- **前端**: Vue 3 + TypeScript + Vite + Naive UI + Pinia
- **流程引擎**: Snakemake 8.0+
- **AI**: Cherry Studio SSE 架构 + Kimi/OpenAI API + MCP SDK
- **部署**: Docker Compose（主栈 + 独立 Worker 栈，逻辑解耦）

## 快速开始

### 环境要求

- Python >= 3.11
- Node.js >= 18
- Docker >= 24.0
- uv (Python 包管理器)

### 本地开发

```bash
# 1. 检查环境变量（.env 已存在，按需编辑）
#    编辑 .env，设置 JWT_SECRET_KEY、AL_API_KEY 等

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

OmicHub 的 Web 控制面与 Celery Worker 计算面已拆分为**两个独立编排栈**，通过外部网络 `omichub_net` 共享 Redis，并经宿主目录 `/data/omichub` 共享任务数据：

- **主栈** `docker-compose.yml`：`web` / `db` / `redis` / `nginx` / `beat` / `flower`
- **Worker 栈** `docker-compose.worker.yml`：仅 `worker`，挂载宿主 conda 与流程代码

```bash
# 0. 宿主目录前置（首次部署，需 sudo；让 web 与 worker 共享同一任务数据目录）
sudo mkdir -p /data/omichub
sudo chown $USER:$USER /data/omichub

# 1. 检查环境变量（.env 已存在，按需编辑）
#    必须修改：
#    - JWT_SECRET_KEY（随机长字符串）
#    - AL_API_KEY（阿里云 DashScope API Key）
#    - OMICHBUB_INIT_ADMIN_PASSWORD（生产环境必填）
#    - AI_CONFIG_ENCRYPTION_KEY（固定值，用于加密 API Key）

# 2. 构建前端
cd frontend && npm install && npm run build && cd ..

# 3. 启动主栈（自动创建跨栈外部网络 omichub_net）
make docker-up

# 4. 启动独立 Worker 栈（计算节点）
make docker-up-worker

# 5. 执行数据库迁移
docker exec omichub-web uv run alembic upgrade head

# 6. 初始化管理员账号
docker exec omichub-web uv run python scripts/init_admin.py

# 7. 初始化饼干定价策略（可选）
docker exec omichub-web uv run python scripts/init_cookies.py

# 8. 访问
# 开发环境: http://localhost:8888
```

> 💡 一键拉起主栈 + Worker（含前端构建）：`make docker-up-all`；改动前端后刷新：`make docker-reload`。

### 生产环境部署

```bash
# 主栈：使用生产环境 override（4 uvicorn worker + 不暴露 DB 端口 + SSL）
docker compose -f deploy/docker/docker-compose.yml \
               -f deploy/docker/docker-compose.prod.yml up -d

# Worker 栈：独立启动（生产水平扩展用 --scale）
docker compose -f deploy/docker/docker-compose.worker.yml --scale worker=2 up -d
```

> 注意：两栈必须通过同一外部网络 `omichub_net` 连通，且共享同一宿主 `/data/omichub`。首次需先执行 `docker network create omichub_net`（或 `make docker-network`）。

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

按破坏性分级，优先使用 `make` 命令：

```bash
# ① 轻度清理：仅删除两栈容器 + 网络（含孤儿容器），保留数据库/Redis 数据卷与镜像
make docker-clean

# ② 彻底重置（⚠️ 不可逆）：两栈容器 + 数据卷(pg_data/redis_data) + 网络 + 本地构建镜像
make docker-purge
```

> 注：任务数据存放于宿主 `/data/omichub`（bind mount，非数据卷），`make docker-purge` **不会**删除它。需彻底清理任务数据请手动 `sudo rm -rf /data/omichub`。

清理后重新拉起并初始化：

```bash
make docker-up-all
docker exec omichub-web uv run alembic upgrade head
docker exec omichub-web uv run python scripts/init_admin.py   # 首次部署需要
docker exec omichub-web uv run python scripts/init_cookies.py # 可选
```

> ⚠️ `make docker-purge` 会清空 `pg_data` 数据卷，相当于删库。执行前确认无需保留的实验/任务数据，或先备份。

补充命令（手动场景）：

```bash
# 仅停止容器（等同 docker-clean 但不重建）
make docker-down

# 清理 Docker 构建缓存和悬挂镜像
docker builder prune -f
docker image prune -f

# 彻底清理所有 OmicHub 相关资源（含拉取镜像，⚠️ 不可恢复）
docker compose -f deploy/docker/docker-compose.yml down -v --rmi all
docker compose -f deploy/docker/docker-compose.worker.yml down -v --rmi all
docker volume rm $(docker volume ls -q | grep omichub) 2>/dev/null
sudo rm -rf /data/omichub   # 任务数据（bind mount）
```

### 账号密码重置

如果只是忘记管理员密码，不需要删除数据库，直接重置即可：

```bash
# 进入 web 容器
docker exec -it omichub-web bash

# 重置 admin 密码为 admin123（开发环境）
python - <<'PY'
import asyncio
from omichub.core.security import hash_password
from omichub.infrastructure.database.session import get_session_factory
from omichub.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository

async def reset():
    factory = get_session_factory()
    async with factory() as session:
        repo = SqlAlchemyUserRepository(session)
        user = await repo.get_by_username("admin")
        if not user:
            print("未找到 admin 用户")
            return
        user.hashed_password = hash_password("admin123")
        await repo.save(user)
        print("admin 密码已重置为 admin123，请登录后立即修改")

asyncio.run(reset())
PY
```

重置后使用 `admin / admin123` 登录，并在 **系统设置 → 个人中心** 修改为强密码。

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
make docker-up-all
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
  docker-compose.yml  主栈开发环境 (web/db/redis/nginx/beat/flower)
  docker-compose.worker.yml  独立 Worker 计算栈
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
| `make docker-network` | 创建跨栈外部网络 omichub_net（幂等） |
| `make docker-up` | 启动主栈 (web/db/redis/nginx/beat/flower) |
| `make docker-up-worker` | 启动独立 Worker 计算栈 |
| `make docker-up-all` | 启动主栈 + Worker（一键全启） |
| `make docker-down-all` | 停止主栈 + Worker |
| `make docker-logs-worker` | 查看 Worker 日志 |
| `make docker-reload` | 重新构建前端并刷新主栈 + Worker |
| `make docker-clean` | 清理两栈容器与网络（保留数据卷） |
| `make docker-purge` | [危险] 彻底清理：容器+数据卷+网络+本地镜像 |
| `make init-admin` | 初始化管理员账号 |
| `make init-cookies` | 初始化饼干定价策略 |
| `make clean` | 清理 Python 缓存文件 |

## 流程（Flow）扩展机制

OmicHub 采用 **YAML 声明式 + 通用构建器** 的架构来接入不同的 Snakemake 分析流程。新增流程时，**通常只需要在 `flows/` 目录下添加 YAML 配置文件**，无需修改后端 Python 代码。

### 流程加载方式

1. 服务启动后，首次访问 `/api/v1/flows` 时会懒加载 `flows/` 目录下所有 `*.yaml` / `*.yml` 文件；
2. 文件由 `FlowDomainService` 用 Pydantic 模型校验结构、参数唯一性、条件渲染引用等；
3. 校验通过的流程会缓存在内存中，以 `meta.id` 为唯一键；
4. 新增或修改 YAML 后，调用 `POST /api/v1/flows/reload` 即可热重载，无需重启服务。

### 核心设计

后端 `TaskService` 不再针对每个流程写 `if-elif` 分支，而是统一调用 `GenericFlowBuilder`。该构建器读取 YAML 中的 `pipeline_mapping` 节点，动态完成：

- 生成主配置文件（`config.yaml` / `analysis.yaml` 等，由 `execution.config_file_name` 指定）；
- 生成样本表 `samples.csv`；
- 生成差异比较组表 `contrasts.csv`（可选）；
- 注入动态计算字段（工作目录、样本表路径、比较组路径）。

### 新增一个分析流程的步骤

以新增 `chip_seq` 为例：

1. **创建 YAML 文件** `flows/chip_seq.yaml`，至少包含：
   - `meta`：流程元信息（`id` 必须全局唯一且符合 `^[a-z][a-z0-9_]*$`）；
   - `parameters`：前端动态表单参数定义；
   - `execution`：Snakefile 路径、资源配置、主配置文件名；
   - `sample_sheet`：样本表校验规则；
   - `pipeline_mapping`：参数到底层流程输入文件的映射规则。

2. **编写 `pipeline_mapping`**：

   ```yaml
   pipeline_mapping:
     config_fields:           # 直接写入主配置文件的字段
       - project_name
       - Genome_Version
       - species
       - raw_data_path
       - peak_calling.macs2_qvalue   # 支持点号生成嵌套字典
     computed_fields:         # 由构建器动态注入的字段
       workflow: "__work_dir__"
       sample_csv: "__samples_csv__"
       paired_csv: "__contrasts_csv__"
     list_fields:             # 强制转为字符串列表的字段
       - raw_data_path
     sample_sheet:
       output_name: "samples.csv"
       columns:
         sample: sample
         sample_name: sample_name
         group: group
     comparisons:
       output_name: "contrasts.csv"
       columns:
         Control: Control
         Treat: Treat
   ```

3. **放置 Snakefile**：确保 `execution.snakefile` 指向的 Snakemake 文件存在，并能读取生成的配置文件；

4. **热重载**：

   ```bash
   curl -X POST http://localhost:8000/api/v1/flows/reload \
        -H "Authorization: Bearer <token>"
   ```

   或直接重启后端服务。

5. **前端使用**：访问 `/api/v1/flows/chip_seq/schema` 可获取参数 JSON Schema，前端据此渲染表单；提交任务时 `/api/v1/tasks/submit` 的 `flow_id` 填 `chip_seq` 即可。

### 已有流程配置参考

- `flows/rna_seq.yaml` — RNAFlow 流程，主配置文件 `config.yaml`
- `flows/atac_seq.yaml` — ATACFlow 流程，主配置文件 `analysis.yaml`

### 注意事项

- `meta.id` 一旦确定尽量不要修改，数据库中的任务记录会关联该 ID；
- `pipeline_mapping` 缺失的流程只会被展示和解析，**无法提交执行**；
- 若某字段需要嵌套结构（如 `peak_calling.use_pooled_peaks`），在 `config_fields` 中使用点号路径即可；
- 所有字段默认值、动态占位符、类型转换规则均可在 `pipeline_mapping` 中声明。

## 文档

详细架构设计见 `docs/` 目录：

- `OmicHub_CherryStudio_整合实施文档.md` — AI 助手 Cherry Studio SSE 架构
- `OmicHub_完整系统架构设计文档_v3.md` — 整体架构设计
- `modules/` — 各模块详细设计
