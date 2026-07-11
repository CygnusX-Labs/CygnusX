# 快速开始

## 环境要求

| 组件 | 最低版本 |
|---|---|
| Python | 3.11 |
| Node.js | 18 |
| Docker | 24.0 |
| uv | 最新 |

## 本地开发

```bash
# 1. 安装后端依赖
uv sync

# 2. 安装前端依赖
cd frontend && npm install

# 3. 启动 PostgreSQL + Redis
make docker-up

# 4. 执行数据库迁移
make migrate

# 5. 初始化管理员
make init-admin

# 6. 启动后端开发服务器
make dev

# 7. 启动前端开发服务器
make frontend-dev
```

访问前端 `http://localhost:5173`，API 文档 `http://localhost:8000/docs`。

## Docker 一键部署（推荐）

```bash
# 准备数据目录
sudo mkdir -p /data/omichub
sudo chown $USER:$USER /data/omichub

# 构建前端
cd frontend && npm install && npm run build && cd ..

# 启动主栈与 Worker 栈
make docker-up
make docker-up-worker

# 数据库迁移与初始化
docker exec omichub-web uv run alembic upgrade head
docker exec omichub-web uv run python scripts/init_admin.py
```

生产环境部署与检查项见 [生产环境检查清单](deployment/production-checklist)。
