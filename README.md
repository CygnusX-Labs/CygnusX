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
#    命令行：make init-admin
#    或浏览器访问 http://localhost:5173/setup 网页注册（见下方「首次使用与管理员注册」）
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

# 6. 初始化管理员账号（二选一，推荐方式 A）
#    方式 A：浏览器访问 /setup 网页注册（见下方「首次使用与管理员注册」）
#    方式 B：命令行脚本
docker exec omichub-web uv run python scripts/init_admin.py

# 7. 初始化饼干定价策略（可选）
docker exec omichub-web uv run python scripts/init_cookies.py

# 8. 访问
# 开发环境: http://localhost:8888
```

> ⚠️ **改前端后必须重启 nginx 才能生效**：nginx 通过 bind mount 挂载 `frontend/dist`，
> 但 `docker up -d` **不会重启已运行的容器**。Vite 构建会清空重建 dist（新 inode），
> 旧的 nginx 进程仍持有旧目录句柄，导致页面不更新。
> - 改动前端后用：`make docker-reload`（含 build + restart nginx）
> - 或手动：`cd frontend && npm run build && cd .. && docker restart omichub-nginx`
> - 浏览器端强制刷新：Ctrl+Shift+R（避免缓存旧 chunk）

### 首次使用与管理员注册

平台首次部署、数据库尚无管理员账号时，可直接用浏览器打开「初始化配置」页创建首位管理员：

```
http://<服务器IP>:8888/setup        # 例：http://192.168.5.102:8888/setup
```

- 该页面仅在**系统无任何 admin 用户**时可用（后端 `has_any_admin()` 强制校验）。
- 一旦首位管理员创建成功，`/setup` 即被永久关闭：
  - 浏览器再次访问 `/setup` 会自动重定向到登录页；
  - 即便绕过前端直接 `POST /api/v1/auth/setup`，后端也会返回 `409 系统已存在管理员账号，请通过登录页访问`，无法再创建第二个管理员。
- 因此 `/setup` 不存在被反复打开注册管理员的安全风险。

> 首位管理员创建后，其他账号需由管理员在「系统管理 → 用户管理」中创建（或在开放自助注册时通过登录页注册）。首次登录会自动弹出迎新引导，并收到一条指向「实验室知识库」的欢迎通知。

> 💡 一键拉起主栈 + Worker（含前端构建）：`make docker-up-all`。

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

按破坏性分级，四个命令职责清晰：

| 命令 | 容器 | 数据卷 | 镜像 | 前端 dist | 用途 |
|------|------|--------|------|-----------|------|
| `docker-clean` | down | 保留 | 保留 | 保留 | 停服务，数据不动 |
| `docker-reload` | restart | 保留 | 保留 | 重建 | 开发时刷代码 |
| `docker-purge` | down + 强制删除 | 清空 | 删除 | 删除 | 只清理，不启动 |
| `docker-start` | purge + build + up | 清空 | 重建 | 重建 | 彻底重建，从头启动 |

```bash
# ① 轻度清理：仅删除两栈容器 + 网络（含孤儿容器），保留数据库/Redis 数据卷与镜像
make docker-clean

# ② 彻底清理（⚠️ 不可逆）：容器 + 数据卷 + 网络 + 本地镜像 + 前端构建产物，只清理不启动
make docker-purge

# ③ 彻底重建（⚠️ 不可逆）：在 purge 基础上重建镜像 + 构建前端 + 启动全部服务
make docker-start
```

> 注：任务数据存放于宿主 `/data/omichub`（bind mount，非数据卷），`make docker-purge` **不会**删除它。需彻底清理任务数据请手动 `sudo rm -rf /data/omichub`。

`docker-start` 清理后会自动重建并启动，无需手动执行 `docker-up-all`。`docker-purge` 清理后需手动拉起：

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
    components/       组件 (ai-chat/ admin/ sandbox/ knowledge/ dashboard/)
    composables/      组合式函数 (useChatStream/useAIWebSocket/...)
    stores/           Pinia 状态 (chatSession/chatAssistant/ai/auth/...)
    views/            页面
deploy/docker/        Docker 部署配置
  docker-compose.yml  主栈开发环境 (web/db/redis/nginx/beat/flower)
  docker-compose.worker.yml  独立 Worker 计算栈
  docker-compose.prod.yml  生产环境 override
  nginx/nginx.conf   nginx 配置 (bind mount 挂载 frontend/dist)
flows/                Snakemake 流程 YAML (rna_seq/atac_seq)
data/                 AI Provider YAML 配置
docs/                 架构设计文档
  knowledge/         实验室知识库 (meta.yaml 导航 + *.md 正文)
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
| `make docker-purge` | [危险] 彻底清理：容器+数据卷+网络+本地镜像+前端产物 |
| `make docker-start` | [危险] 彻底重建：purge + 重建镜像 + 构建前端 + 启动全部服务 |
| `make init-admin` | 初始化管理员账号 |
| `make init-cookies` | 初始化饼干定价策略 |
| `make check-migrations` | 静态检查 Alembic 迁移链完整性 |
| `make check-alembic-heads` | 检查数据库是否存在 Alembic 多分支 (Multiple Heads) |
| `make clean` | 清理 Python 缓存文件 |

## 数据库迁移

### 创建新迁移

```bash
make migrate-new m="add xxx table"
```

### 迁移链健康检查

新增或修改迁移文件后，务必运行静态检查，确保 `down_revision` 等依赖关系正确：

```bash
make check-migrations
```

`make check-migrations` 会在**不连接数据库**的情况下解析所有迁移文件，检查：

- 每个迁移文件都能正确解析 `revision`、`down_revision`、`depends_on`。
- `down_revision` / `depends_on` 指向的父迁移真实存在。
- 迁移链只有一个 root，且拓扑连通（无孤岛）。
- 最终 `alembic heads` 唯一。

**建议在以下场景执行：**

- 新建或修改了 `alembic/versions/` 下的迁移文件。
- 合并分支后迁移文件有冲突。
- 拉取他人代码后，本地发现 `alembic/versions/` 有新增文件。
- 提交代码前或 CI 流水线中。

如果检查失败，说明迁移链本身有问题，**不要提交、不要部署**，先修好 `down_revision` 再推进。

### 常见迁移错误

#### `down_revision` 指向错误父节点

例如迁移 `g3h4i5j6k7l8_add_model_name_to_agent_templates.py` 的作用是向 `agent_templates` 表添加字段，因此它的 `down_revision` 必须指向创建 `agent_templates` 表的迁移 `9a5b6c7d8e1f`。如果错指向 `c2d3e4f5a6b7`（目录表迁移），则空库从头升级时会因表不存在而报错：

```
sqlalchemy.exc.ProgrammingError: relation "agent_templates" does not exist
```

修复方式：修正迁移文件中的 `down_revision`。

#### Alembic Multiple Heads（多分支）

当多人并行创建迁移且未正确合并时，可能出现多个 head。可通过以下方式检查：

```bash
make check-alembic-heads
```

若发现多分支，执行：

```bash
make migrate-merge
```

## 代码更新后如何更新容器

根据改动类型选择对应的更新命令，避免不必要的镜像重建或数据清理：

| 改动类型 | 推荐命令 | 说明 |
|---|---|---|
| 只改前端代码（`frontend/src/`） | `make docker-reload` | 重新构建 `frontend/dist`，并重启 nginx / web |
| 只改后端 Python 源码（`src/`） | `docker restart omichub-web omichub-beat omichub-worker` | 容器挂载 `src:ro`，重启即可加载新代码，无需重建镜像 |
| 改了流程 YAML（`flows/*.yaml`） | `curl -X POST http://localhost:8000/api/v1/flows/reload` | 流程支持热重载，无需重启服务 |
| 改了数据库模型或新增迁移文件 | 先 `make check-migrations`，再 `make docker-reload` | web 容器入口会自动执行 `alembic upgrade head` |
| 改了依赖（`pyproject.toml` / `uv.lock`）或 Dockerfile | `make docker-start` | 必须重建镜像；这会清空数据卷，开发环境可用，生产环境需谨慎 |
| 想彻底从零重建 | `make docker-start` | 执行 `docker-purge + build --no-cache + 构建前端 + up` |

### 日常迭代推荐

前端 + 后端源码的日常改动，统一用：

```bash
make docker-reload
```

它等价于：

```bash
cd frontend && npm run build
docker compose -f deploy/docker/docker-compose.yml restart nginx
docker compose -f deploy/docker/docker-compose.yml restart web
docker compose -f deploy/docker/docker-compose.yml up -d
docker compose -f deploy/docker/docker-compose.worker.yml up -d
```

> ⚠️ `make docker-reload` **不会重建镜像，也不会删除数据卷**。如果改了 `pyproject.toml`、Dockerfile 或需要彻底清空环境，请用 `make docker-start`。

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

## 数据下载（EBIDownload）

平台内置「数据下载」入口，调用 Rust 写的 [EBIDownload](pipelines/EBIDownload) 工具从 EBI/NCBI 下载测序数据（FASTQ）。下载完成的数据**自动出现在「数据管理」中**（FASTQ 类型），可直接作为分析流程的输入。该功能默认关闭，按以下步骤启用：

### 1. 构建 Rust 二进制

```bash
cd pipelines/EBIDownload
CC=clang cargo build -p ebidownload-cli --release
# 产物：target/release/EBIDownload
```

### 2. 装运行时依赖

Worker 需要 `sra-tools`（`prefetch` / `fasterq-dump`）。宿主机或 worker 镜像任选一种方式安装：

```bash
# 方式 A：在 worker 容器/镜像内安装
mamba install -n base -c bioconda sra-tools

# 方式 B：用 EBIDownload 自带命令拉取（写入 EBIDownload.yaml 指向的路径）
./EBIDownload deps install
```

### 3. 配置二进制与 YAML 路径

将构建产物与工具配置（`EBIDownload.yaml`，含 sra-tools 路径）放到 `/data/omichub/bin/`（默认路径，可在 `.env` 覆盖）：

```bash
mkdir -p /data/omichub/bin
cp pipelines/EBIDownload/target/release/EBIDownload /data/omichub/bin/EBIDownload
cp pipelines/EBIDownload/EBIDownload.yaml /data/omichub/bin/EBIDownload.yaml
```

对应 `.env` 配置项（均有默认值）：

```env
ENABLE_EBI_DOWNLOAD=true                 # 装好二进制 + sra-tools 后再开
EBI_DOWNLOAD_BINARY=/data/omichub/bin/EBIDownload
EBI_DOWNLOAD_YAML=/data/omichub/bin/EBIDownload.yaml
```

### 4. 端到端验证

1. 访问前端「数据下载」页面（`/downloads`），输入一个公开登录号（如 `PRJNA1251654` 或单个 `SRRxxxxxx`），提交下载任务；
2. 跳转任务详情页，可见任务状态为 RUNNING、EBIDownload 的 JSON 日志实时回写、下载进度条推进；
3. 任务 SUCCESS 后，刷新「数据管理」（`/files`）即可看到 `ebi_download/<accession>/` 下的 FASTQ 文件（类型标记为 FASTQ）。

> 说明：下载产物落在 `storage_path/upload_dir/<user_id>/ebi_download/<accession>/`，复用文件系统的扫描入库机制，无需额外建表。FASTQ 体量较大，请确认 `/data/omichub` 所在磁盘容量充足。

## 实验室知识库（Knowledge Base）

知识库页面（`/knowledge`）采用「树形目录 + 沉浸式 Markdown 阅读 + 管理员在线编辑」的专业文档系统，基于 [md-editor-v3](https://github.com/imzbf/md-editor-v3) 实现。

### 数据来源与自动加载

知识库文档以纯文件形式存储在 `docs/knowledge/` 目录：

- `docs/knowledge/meta.yaml` —— 导航配置（标题、文档列表、可选 `category` 分类）
- `docs/knowledge/*.md` —— Markdown 正文

服务每次读取文档时**直接读盘**，因此保存后无需重启即可生效（重启后自动加载最新内容，无 DB 持久化）。

```yaml
# docs/knowledge/meta.yaml 示例
title: "实验室知识库"
items:
  - id: "getting-started"
    title: "快速入门"
    file: "getting-started.md"
    category: "上手指南"      # 可选，前端按它聚合成树形目录
  - id: "rna-seq-tips"
    title: "RNA-seq 分析小贴士"
    file: "rna-seq-tips.md"
    category: "流程说明"
```

### 在线编辑（管理员）

- **阅读模式**：左侧树形目录（按 `category` 分组）+ 右侧 `MdPreview` 预览（80%）+ `MdCatalog` 大纲导航（20%，sticky）。
- **编辑模式**（仅管理员可见「编辑」按钮）：满宽 `MdEditor` 编辑器；点「保存」回写 `docs/knowledge/<file>.md` 落盘，下次加载即为新内容；点「取消」还原。
- 接口：`GET /api/v1/docs/knowledge`（目录）、`GET /api/v1/docs/knowledge/{doc_id}`（正文）、`PUT /api/v1/docs/knowledge/{doc_id}`（保存，需管理员）。

### 安全

- 保存接口带路径遍历防护：`resolve()` 后必须仍在 `docs/knowledge/` 目录内，且只能改已配置条目对应的文件，禁止凭空新建或越权写盘。
- 原子写：先写 `.tmp` 再 `replace`，避免写一半损坏文件。

> 新增文档：在 `meta.yaml` 的 `items` 加一条，并在 `docs/knowledge/` 放对应 `.md` 文件即可（可热更新，无需迁移）。

## 文档

详细架构设计见 `docs/` 目录：

- `OmicHub_CherryStudio_整合实施文档.md` — AI 助手 Cherry Studio SSE 架构
- `OmicHub_完整系统架构设计文档_v3.md` — 整体架构设计
- `modules/` — 各模块详细设计
