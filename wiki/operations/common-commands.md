# 常用命令

## 本地开发

| 命令 | 说明 |
|---|---|
| `make dev` | 启动后端开发服务器 |
| `make frontend-dev` | 启动前端开发服务器 |
| `make dev-worker` | 启动 Celery Worker |
| `make dev-beat` | 启动 Celery Beat |
| `make dev-flower` | 启动 Flower 监控 |

## 代码质量

| 命令 | 说明 |
|---|---|
| `make test` | 运行测试 |
| `make test-cov` | 运行测试并生成覆盖率 |
| `make lint` | Ruff 静态检查 |
| `make format` | Ruff 格式化与自动修复 |
| `make type-check` | Mypy 类型检查 |

## Docker 生命周期

| 命令 | 容器 | 数据卷 | 镜像 | 用途 |
|---|---|---|---|---|
| `make docker-up` | up | 保留 | 保留 | 启动主栈 |
| `make docker-up-worker` | up | 保留 | 保留 | 启动 Worker 栈 |
| `make docker-up-all` | up | 保留 | 保留 | 一键全启 |
| `make docker-down-all` | down | 保留 | 保留 | 停止全栈 |
| `make docker-reload` | restart | 保留 | 保留 | 前端/后端代码刷新 |
| `make docker-clean` | down | 保留 | 保留 | 清理容器与网络 |
| `make docker-purge` | down+删除 | 清空 | 删除 | 彻底清理 |
| `make docker-start` | purge+build+up | 清空 | 重建 | 彻底重建 |

## 数据库与初始化

| 命令 | 说明 |
|---|---|
| `make migrate` | 执行 Alembic 迁移 |
| `make migrate-new m="..."` | 创建新迁移 |
| `make migrate-merge` | 合并多分支 |
| `make init-admin` | 初始化管理员 |
| `make init-cookies` | 初始化饼干定价 |

## 前端更新

前端改动后必须让 nginx 加载新的 `frontend/dist`：

```bash
make docker-reload
```

或手动：

```bash
cd frontend && npm run build
docker restart omichub-nginx
```
