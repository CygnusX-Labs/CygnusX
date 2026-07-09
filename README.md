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

详细的 Makefile 命令说明见 [docs/Makefile_命令说明.md](docs/Makefile_命令说明.md)。

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

> 注：任务数据存放于宿主 `/data/omichub`（bind mount，非数据卷），`make docker-purge` **不会**删除它。其中 `omichub_data/_pgdata` 是数据库目录、`omichub_data/_redis` 是缓存目录。需彻底清理任务数据请手动 `sudo rm -rf /data/omichub`。

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
tools/                生信工具箱工具配置 (YAML 热重载)
  terminal/           云端沙盒终端 (Dockerfile + terminal_config.yaml)
  jbrowse/            JBrowse 2 基因组浏览器配置
  enrichments/        KEGG/GO 富集分析物种配置
data/                 AI Provider YAML 配置
docs/                 架构设计文档
  knowledge/         实验室知识库 (meta.yaml 导航 + *.md 正文)
```

## 数据目录结构

平台运行时数据统一收口在宿主机 `/data/omichub`（由 `data/OmicHub.yaml` 的 `storage.data_root` 声明）。**数据库、缓存、参考基因组、知识库、欢迎词**五类核心数据已集中迁至 `omichub_data/` 子目录，让数据区更清爽；用户上传、任务产物等仍直接落在根下。

```
/data/omichub/                      # 数据根目录（storage.data_root）
├── omichub_data/                   # ★ 集中数据区
│   ├── _pgdata/                    # PostgreSQL 数据库（bind mount，uid 70 / 700）
│   ├── _redis/                     # Redis 持久化 dump.rdb（bind mount，uid 999）
│   ├── jbrowse/                    # JBrowse 2 参考基因组 + 预设轨道（ref/ tracks/）
│   ├── knowledge/                  # 实验室知识库运行时副本（镜像自 docs/knowledge/）
│   └── welcome/                    # 管理员登录欢迎词（welcome.yaml + 轮询游标）
├── users/<user_id>/                # 用户私有数据（上传 / 结果 / 富集产物）
├── uploads/                        # 分片上传中转
├── bin/                            # 外置二进制（EBIDownload 等）
├── dataset/                        # 公共数据集
└── .tmp/                           # 临时文件
```

### omichub_data 各子目录

| 子目录 | 作用 | 挂载 / 配置来源 | 备注 |
|--------|------|-----------------|------|
| `_pgdata/` | PostgreSQL 全部关系型数据（账号/任务/AI 会话） | `db` 服务 bind mount → `/var/lib/postgresql/data` | 属主 postgres(uid 70)，`rsync` 需 `-a` 保留属主；停库后再迁移 |
| `_redis/` | Redis 持久化 + Celery 队列 + 限流缓存 | `cache` 服务 bind mount → `/data` | 属主 redis(uid 999)；缓存类数据，丢失可重建 |
| `jbrowse/` | 参考基因组 FASTA(3.3G) + 基因注释(3.2G) | `tools/jbrowse/jbrowse_config.yaml` 绝对路径 | 经 nginx `/tracks/` 流式读取；位于 `data_root` 下，换算自动兼容 |
| `knowledge/` | 知识库 `meta.yaml` + `*.md` + 配图 | 镜像自仓库 `docs/knowledge/` | 在线编辑读仓库源；此为数据区备份副本 |
| `welcome/` | 预生成欢迎词数组 + 轮询游标 | `config.py` 的 `welcome_yaml` / `welcome_state_yaml` | 启动时不足 20 条自动调 AI 补齐 |

### 为什么这些路径不用改容器挂载

`omichub_data` 仍是 `data_root`（`/data/omichub`）的子目录，因此：

- 容器内 `/data/omichub` 挂载、nginx `/tracks/` alias、`storage.data_root` 均**未改动**；
- `to_tracks_uri()` 把绝对路径换算为 `/tracks/omichub_data/jbrowse/...`，nginx 天然可读；
- 仅需同步修改 `docker-compose.yml` / `docker-compose.prod.yml` 的 `db`/`cache` bind mount、`config.py` 的 welcome 路径、`jbrowse_config.yaml` 的 fasta/轨道路径。

### 快速备份 / 迁移

```bash
# 停服后增量同步整个数据根（含 omichub_data）
docker compose -f deploy/docker/docker-compose.yml down
docker compose -f deploy/docker/docker-compose.worker.yml down
sudo rsync -aP --info=progress2 /data/omichub/ <目标机>:/data/omichub/
```

## 日志排查

平台日志统一收口到宿主机 `/data/omichub/logs/`。应用日志、Celery 单任务日志、Nginx 日志、Snakemake stdout/stderr 均有明确的容量保护策略。

### 目录结构

```text
/data/omichub/logs/
├── app/                          # web / beat / worker 应用日志
│   ├── omichub.log
│   ├── omichub.json.log
│   └── error.log
├── celery/                       # Celery 单任务日志
│   └── tasks/{task_id}.log
├── nginx/
│   ├── access.log
│   └── error.log
└── snakemake/
    └── {project_name}/{timestamp}/
        ├── stdout.log
        └── stderr.log
```

### 首次初始化

新机器或清空数据后执行一次：

```bash
sudo mkdir -p /data/omichub/logs/{app,celery/tasks,nginx,snakemake}
sudo chown -R ${PUID:-1000}:${PGID:-1000} /data/omichub/logs
sudo chmod -R 755 /data/omichub/logs
```

如需启用宿主机 logrotate 兜底 Nginx/Snakemake 文件日志：

```bash
sudo cp deploy/logrotate/omichub-logs /etc/logrotate.d/omichub-logs
sudo logrotate -d /etc/logrotate.d/omichub-logs
```

### 常用排查命令

```bash
# 实时跟踪应用日志
tail -f /data/omichub/logs/app/omichub.log

# 只看 ERROR
tail -f /data/omichub/logs/app/error.log

# 按任务查 Celery 文件日志
tail -f /data/omichub/logs/celery/tasks/{task_id}.log

# 查看最近一次 Snakemake stdout/stderr
ls -lt /data/omichub/logs/snakemake/{project_name}/

# JSON 日志按服务过滤（需 jq）
jq 'select(.record.extra.service == "audit")' /data/omichub/logs/app/omichub.json.log

# Nginx 5xx 请求
jq 'select(.status >= 500)' /data/omichub/logs/nginx/access.log
```

### 容量保护

| 日志类型 | 策略 | 默认值 |
|------|------|------|
| 应用日志 | loguru rotation/retention/compression | `50 MB` / `30 days` / `zip` |
| Celery 单任务日志 | loguru rotation/retention/compression | `20 MB` / `7 days` / `zip` |
| Docker stdout/stderr | Docker `json-file` 限制 | `50m` × `3` |
| Nginx 文件日志 | 宿主机 logrotate | `100M` 或 daily，保留 14 轮 |
| Snakemake 文件日志 | 宿主机 logrotate + 定时清理 | `200M` 或 daily，建议 30 天清理 |
| DB 任务日志 | repository 截断 | 单条 8192 字符，单任务最近 1000 条 |

### 环境变量

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SERVICE_NAME` | 服务标识（web/beat/worker） | `app` |
| `OMICHUB_LOG_LEVEL` | stdout 日志级别 | `INFO`（开发环境 DEBUG） |
| `OMICHUB_LOG_DIR` | 应用日志根目录 | `/app/logs` |
| `OMICHUB_LOG_ROTATION` | 应用日志轮转阈值 | `50 MB` |
| `OMICHUB_LOG_RETENTION` | 应用日志保留期 | `30 days` |
| `OMICHUB_LOG_COMPRESSION` | 应用日志压缩格式 | `zip` |
| `OMICHUB_CELERY_LOG_DIR` | Celery 单任务日志目录 | `${OMICHUB_LOG_DIR}/celery/tasks` |
| `OMICHUB_CELERY_LOG_ROTATION` | Celery 单任务日志轮转阈值 | `20 MB` |
| `OMICHUB_CELERY_LOG_RETENTION` | Celery 单任务日志保留期 | `7 days` |
| `OMICHUB_CELERY_LOG_COMPRESSION` | Celery 单任务日志压缩格式 | `zip` |
| `TASK_LOG_MESSAGE_MAX_CHARS` | DB 单条任务日志 message 最大字符数 | `8192` |
| `TASK_LOG_MAX_ENTRIES` | DB 单任务最多保留日志条数 | `1000` |

详细架构说明见项目根目录 `LOG_ARCHITECTURE.md`。

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
| `make docker-fix-permissions` | 修复 `/data/omichub` 日志/用户目录权限事故 |
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

### Docker 权限事故恢复

如果 `make docker-reload` 后登录页提示“系统内部错误”，并且 `docker logs omichub-web` 出现类似：

```text
PermissionError: [Errno 13] Permission denied: '/app/logs/omichub.log'
```

说明宿主机 `/data/omichub/logs/app` 等 bind mount 目录被 root 创建或属主漂移，而 `web/worker` 容器按非 root 的 `1000:1000` 运行，无法写日志。执行：

```bash
make docker-fix-permissions
docker restart omichub-web omichub-worker omichub-beat
```

`docker-up`、`docker-up-worker`、`docker-up-all`、`docker-start`、`docker-reload` 已经会自动执行轻量版运行目录准备，正常情况下不需要手动处理。

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

## 数据下载与聚合（公共数据库 + 云存储）

平台内置「数据下载」入口（`/downloads`），统一承载公共数据库下载与云对象存储直拉。所有下载都会创建通用 `Task` 聚合根（历史 `flow_id="ebi_download"`，语义已扩展为 Data Download），任务日志、状态、进度、任务详情页和文件入库都复用现有任务系统，不额外创建 `download_tasks` / `download_files` 表。

### 架构

```text
Vue 下载页 (/downloads)
  ├─ 公共数据库：accession + method
  └─ 云存储：provider + object_uri + recursive
        │ POST /api/v1/downloads
        ▼
DownloadService
  ├─ 校验来源参数与目标目录
  ├─ 创建 Task(flow_id="ebi_download")
  └─ 投递 Celery run_download(task_id)
        ▼
Celery 下载任务
  ├─ source=sra           → EBIDownload + Progress API + Redis download_progress:{task_id}
  └─ source=cloud_storage → ossutil/tosutil/obsutil + stdout/stderr 进度解析
        ▼
TaskRepository + Redis Pub/Sub
  ├─ 回写 Task.status / Task.progress / Task.logs
  └─ 任务详情页实时展示日志与总进度
        ▼
_register_downloaded_files
  └─ 扫描 work_dir，写入 FileRecord，文件自动出现在「数据管理」
```

这套实现采纳了 `docs/26.7.8/OmicHub_云存储下载前后端连接方案.md` 中“前端选择云商 → 后端调用二进制 → 捕获进度 → 前端展示”的核心思路；未采纳新增三张下载表和独立 WebSocket 的部分，因为当前系统已有 Task 聚合、任务日志 WebSocket、Redis 下载进度和文件入库链路。

### 公共数据库下载（EBIDownload）

调用 Rust 写的 [EBIDownload](pipelines/EBIDownload) 工具从 EBI/NCBI 下载测序数据（FASTQ）。下载完成的数据会自动出现在「数据管理」中，可直接作为分析流程输入。该功能默认关闭，启用步骤如下。

#### 1. 构建 Rust 二进制

```bash
cd pipelines/EBIDownload
CC=clang cargo build -p ebidownload-cli --release
# 产物：target/release/EBIDownload
```

#### 2. 装运行时依赖

Worker 需要 `sra-tools`（`prefetch` / `fasterq-dump`）。宿主机或 worker 镜像任选一种方式安装：

```bash
# 方式 A：在 worker 容器/镜像内安装
mamba install -n base -c bioconda sra-tools

# 方式 B：用 EBIDownload 自带命令拉取（写入 EBIDownload.yaml 指向的路径）
./EBIDownload deps install
```

#### 3. 配置二进制与 YAML 路径

```bash
mkdir -p /data/omichub/bin
cp pipelines/EBIDownload/target/release/EBIDownload /data/omichub/bin/EBIDownload
cp pipelines/EBIDownload/EBIDownload.yaml /data/omichub/bin/EBIDownload.yaml
```

```env
ENABLE_EBI_DOWNLOAD=true
EBI_DOWNLOAD_BINARY=/data/omichub/bin/EBIDownload
EBI_DOWNLOAD_YAML=/data/omichub/bin/EBIDownload.yaml
```

### 云存储直拉（OSS / TOS / OBS）

云存储直拉通过对象存储官方 CLI 在 worker 节点执行下载，当前支持：

| 前端选项 | URI 前缀 | 默认二进制 |
| --- | --- | --- |
| 阿里云 OSS | `oss://bucket/path` | `/data/omichub/bin/ossutil` |
| 火山引擎 TOS | `tos://bucket/path` | `/data/omichub/bin/tosutil` |
| 华为云 OBS | `obs://bucket/path` | `/data/omichub/bin/obsutil` |

启用前需要把对应 CLI 放到 `/data/omichub/bin/`，赋予执行权限，并按云商工具自身规范在 worker 环境中配置访问凭据。OmicHub 当前不保存云厂商 AK/SK，也不新增云存储凭据表。

```env
ENABLE_CLOUD_STORAGE_DOWNLOAD=true
CLOUD_OSSUTIL_BINARY=/data/omichub/bin/ossutil
CLOUD_TOSUTIL_BINARY=/data/omichub/bin/tosutil
CLOUD_OBSUTIL_BINARY=/data/omichub/bin/obsutil
```

### 端到端验证

1. 访问前端「数据下载」页面（`/downloads`）。
2. 公共数据库：输入 `PRJNA1251654` 或单个 `SRRxxxxxx` 后提交；云存储：选择云商并输入 `oss://` / `tos://` / `obs://` URI 后提交。
3. 页面会跳转到任务详情页，可见任务状态、实时日志与总进度。
4. 任务 `success` 后刷新「数据管理」（`/files`），即可看到 `raw_data/<任务目录>/` 下的下载文件。

> 说明：下载产物落在 `storage_path/users/<user_id>/raw_data/<target_directory>/<任务目录>/`。FASTQ/BAM 会按文件后缀识别类型，其余对象以 OTHER 入库。大体量数据请确认 `/data/omichub` 所在磁盘容量充足。

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

## 云端沙盒终端

生信工具箱中的即用即毁隔离容器终端。用户在浏览器中获得交互式 bash shell，容器挂载个人工作目录，退出即销毁。

### 架构

```
浏览器 xterm.js  ──WebSocket──>  FastAPI 双向代理  ──aiohttp WS──>  容器内 ttyd:7681 (bash)
                                      │
                              DockerManager (创建/销毁)
                                      │
                              /data/omichub/users/{uid}/workspace  ←bind mount→  /home/omichub/workspace
```

### 启用与配置

1. 构建镜像（`make docker-reload` 自动执行，或手动）：

   ```bash
   docker build -t omichub/sandbox-terminal:latest tools/terminal/docker/
   ```

2. 确保隔离网络存在（`make docker-reload` 自动创建）：

   ```bash
   docker network create omichub-sandbox-net
   ```

3. 所有运行参数集中在 `tools/terminal/terminal_config.yaml`，修改后**自动热重载**（无需重启）：

   | 关键参数 | 默认值 | 说明 |
   |---------|--------|------|
   | `enabled` | `true` | 功能开关 |
   | `image.name:tag` | `omichub/sandbox-terminal:latest` | 容器镜像 |
   | `default_resources.memory_mb` | `512` | 内存上限 |
   | `lifecycle.idle_timeout` | `1800` (30min) | 空闲超时 |
   | `lifecycle.max_sessions_per_user` | `2` | 单用户最大并发 |
   | `storage.workspace_base` | `/data/omichub/users` | 用户目录基路径 |

### 安全策略

- **根文件系统只读** (`read_only=True`)，仅 workspace 和 tmpfs 可写
- **cap_drop ALL** + **no-new-privileges**，容器内非 root (`user 1000:1000`)
- **内存/CPU/PID 硬限制**，防止单用户耗尽资源
- **目录隔离**：仅挂载 `/data/omichub/users/{uid}/workspace`，无法访问其他用户或系统路径
- **即用即毁**：`auto_remove=True`，容器退出后自动删除

### 预装工具

samtools, bcftools, bedtools, fastqc, seqkit, python3 (numpy/pandas/biopython/pysam), vim, htop, jq

详细架构与代码分布见 `tools/terminal/README.md`。

## 安全加固清单

本章节汇总 `SECURITY_AUDIT.md` 中识别的风险及对应的修复措施。首次部署或升级后请按此清单核对。

### 修复概览

| 编号 | 风险 | 修复位置 | 关键配置/说明 |
|---|---|---|---|
| #1 | 路径穿越 → 任意文件读取 | `file_service.py` / `report_service.py` | `_resolve_abs()` / `_resolve_report_path()` 强制 `resolve().relative_to(storage_root)` 校验 |
| #2 | `/tracks/` 无鉴权暴露用户数据 | `nginx.conf` / `nginx.prod.conf` | 默认启用 RFC1918 内网 IP 白名单 |
| #3 | 生产环境默认 JWT 密钥 | `config.py` | `APP_ENV=production` 时若密钥仍为默认值则启动失败 |
| #4 | Redis 无密码 + 端口暴露 | `docker-compose.yml` / `docker-compose.prod.yml` / `config.py` | 开发环境 `--requirepass`；生产关闭 Redis 宿主端口 |
| #5 | AI Provider key / TOTP secret 明文落盘 | `config.py` | 生产环境强制 `AI_PROVIDER_KEY_ENCRYPTION_KEY` 非空 |
| #6 | MCP stdio/SSE 的 RCE/SSRF | `mcp/client.py` / `mcp_service.py` | SSE URL 禁止内网/IP；stdio 禁止绝对路径与 shell |
| #7 | nginx 缺失安全头 + 聊天上传无校验 | `nginx.conf` / `nginx.prod.conf` / `files.py` | 增加 `X-Frame-Options` 等；上传文件扩展名白名单 |
| #8 | Flower 监控无鉴权 | `docker-compose.yml` / `docker-compose.prod.yml` | 开发环境 `--basic_auth`；生产默认关闭 Flower |
| #9 | 云存储 URI 只校验 scheme | `schemas/download.py` | 按云商校验 endpoint 后缀，禁止 IP 地址 |
| #10 | cookie balance Redis 频道无命名空间 | `cookie_pubsub.py` | 频道名改为 `omichub:cookie_balance:{user_id}` |
| #11 | 登录端点仅全局限流 | `auth.py` / `login_rate_limit.py` | 同一 IP 5 分钟失败 5 次封禁 15 分钟 |
| #12 | 终端会话 ID 熵低 | `terminal_service.py` | 改用 `secrets.token_urlsafe(16)` |
| #13 | WebSocket 异常 detail 回传客户端 | `sandbox.py` | 仅返回通用错误，详细异常进日志 |
| #14 | AI key 可能进异常日志 | `openai_compatible.py` | 日志脱敏：Bearer token / api_key 替换为 `[REDACTED]` |
| #15 | WebSocket 未校验用户禁用状态 | `ai.py` / `terminal.py` / `sandbox.py` / `cookies.py` / `tasks.py` | accept 前查库确认 `status == active` |
| #16 | Chat 附件读取 SSRF | `chat_service.py` | 非本地上传时禁止访问内网/回环/metadata URL |
| #17 | MCP stdio command 路径遍历 / args 未校验 | `mcp/client.py` | 禁止 `..`、PATH 白名单、args 禁止 shell 元字符 |
| #18 | AI Tool Call 参数无 schema 校验 | `ai_tools.py` | `TaskSubmitRequest` / `QueryStatusArgs` Pydantic 校验 |
| #19 | 登录限流 XFF 首个 IP 可伪造 | `login_rate_limit.py` | 取 `X-Forwarded-For` 链中最后一个 IP |
| #20 | JWT 无吊销机制 | `security.py` / `deps.py` / `user model` | 引入 `token_version`；改密/角色/状态变更时递增 |
| #21 | 沙盒容器未做网络隔离 | `sandbox/pool.py` / `config.py` | 默认 `sandbox_network_isolated=true` 使用 `network_mode=none` |
| #22 | 聊天文件上传全局可访问 | `files.py` / `chat_service.py` | 目录按 `chat/{user_id}` 隔离；下载校验归属 |
| #23 | TOTP `required` 策略未生效 | `auth_service.py` | `totp_policy=required` 时未绑定 2FA 拒绝登录 |
| #24 | 依赖存在已知 CVE（ecdsa） | `pyproject.toml` / `security.py` | 用 `PyJWT` 替换 `python-jose[cryptography]`，移除 ecdsa 依赖 |

### 首次部署必填环境变量

以下变量在 `.env` 中必须设置为强随机值，生产环境若缺失或仍为默认值应用将**启动失败**。

```bash
# JWT / Cookie 签名密钥（任意长随机字符串，建议 ≥32 字节）
JWT_SECRET_KEY=your-random-secret-here
APP_SECRET_KEY=your-random-secret-here

# Redis 认证密码
REDIS_PASSWORD=your-redis-password-here

# AI Provider key / TOTP secret 加密密钥（Fernet 32 字节 URL-safe base64）
# 生成方式：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AI_PROVIDER_KEY_ENCRYPTION_KEY=your-fernet-key-here

# 开发环境 Flower 基本认证（用户名:密码）
FLOWER_BASIC_AUTH=admin:your-strong-password
```

> ⚠️ `AI_PROVIDER_KEY_ENCRYPTION_KEY` 一旦设置并写入数据后**不可更改**，否则已加密的字段将无法解密。

### `/tracks/` 数据访问说明

`/tracks/` 用于 JBrowse 2 流式读取参考基因组、BAM/VCF 等大文件。默认配置仅允许 RFC1918 内网地址访问：

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`

**公网或多租户部署**不应仅依赖 IP 白名单，建议：

1. 通过 VPN/专线访问；或
2. 实现后端鉴权代理 + nginx `X-Accel-Redirect` 内部重定向。

### MCP 管理安全

MCP Server 注册/调用为**管理员功能**，已做以下限制：

- SSE URL 仅允许 `http`/`https`，禁止指向内网、回环、`169.254.169.254` 等地址。
- stdio command 禁止路径遍历、绝对路径，且必须从 `PATH` 中解析得到；禁止常见 shell 解释器（`sh`/`bash`/`zsh`/`cmd`/`powershell` 等）。
- stdio args 禁止 shell 元字符（`;|&<>()$` 等）与绝对路径/路径遍历。

建议同时启用管理员 2FA、使用强密码，避免管理员凭据泄露后被滥用。

### 生产环境部署检查项

- [ ] `APP_ENV=production`、`APP_DEBUG=false`
- [ ] `JWT_SECRET_KEY`、`APP_SECRET_KEY`、`REDIS_PASSWORD`、`AI_PROVIDER_KEY_ENCRYPTION_KEY` 已设置且非默认值
- [ ] `OMICHBUB_INIT_ADMIN_PASSWORD` 为强密码
- [ ] 数据库端口已在 `docker-compose.prod.yml` 中关闭
- [ ] Redis 端口已在 `docker-compose.prod.yml` 中关闭
- [ ] Flower 服务已在生产关闭（`replicas: 0`）
- [ ] SSL 证书已挂载到 nginx
- [ ] `/tracks/` 仅允许受信内网访问
- [ ] 沙盒容器已启用网络隔离（`SANDBOX_NETWORK_ISOLATED=true`，默认开启）
- [ ] 聊天附件按用户隔离，不存在跨用户访问
- [ ] 依赖漏洞扫描（`pip-audit`）无高危以上漏洞

## 文档

详细架构设计见 `docs/` 目录：

- `OmicHub_CherryStudio_整合实施文档.md` — AI 助手 Cherry Studio SSE 架构
- `OmicHub_完整系统架构设计文档_v3.md` — 整体架构设计
- `modules/` — 各模块详细设计
