# 代码更新与回滚

根据改动类型选择对应的更新命令，可避免不必要的镜像重建或数据清理。

## 改动类型对照表

| 改动类型 | 推荐命令 | 说明 |
|---|---|---|
| 只改前端代码（`frontend/src/`） | `make docker-reload` | 重新构建 `frontend/dist`，并重启 nginx / web |
| 只改后端 Python 源码（`src/`） | `docker restart omichub-web omichub-beat omichub-worker` | 容器挂载 `src:ro`，重启即可加载新代码 |
| 改了流程 YAML（`flows/*.yaml`） | `curl -X POST http://localhost:8000/api/v1/flows/reload` | 流程支持热重载，无需重启服务 |
| 改了数据库模型或新增迁移文件 | 先 `make check-migrations`，再 `make docker-reload` | web 入口会自动执行 `alembic upgrade head` |
| 改了依赖（`pyproject.toml` / `uv.lock`）或 Dockerfile | `make docker-start` | 必须重建镜像；这会清空数据卷，开发环境可用，生产需谨慎 |
| 想彻底从零重建 | `make docker-start` | 执行 `docker-purge + build --no-cache + 构建前端 + up` |

## 日常迭代推荐

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

> `make docker-reload` **不会重建镜像，也不会删除数据卷**。如果改了 `pyproject.toml`、Dockerfile 或需要彻底清空环境，请用 `make docker-start`。

## 彻底重建环境

```bash
make docker-start
```

等价于：

```bash
make docker-purge          # 清空容器、数据卷、网络、本地镜像、前端 dist
cd frontend && npm run build
docker compose -f deploy/docker/docker-compose.yml build --no-cache
docker compose -f deploy/docker/docker-compose.worker.yml build --no-cache
make docker-up-all
```

典型场景：
- 修改了 `pyproject.toml` 新增/删除依赖。
- 修改了 `deploy/docker/Dockerfile`。
- `make docker-reload` 后应用启动报 `ModuleNotFoundError`。
- 想从零开始清理开发环境。

> ⚠️ `make docker-start` 会清空 PostgreSQL 与 Redis 数据卷，开发环境可用；生产环境执行前务必备份。

## 前端不生效排查

改前端后必须重启 nginx：Vite 构建会清空重建 `frontend/dist`（新 inode），旧 nginx 进程仍持有旧目录句柄。

```bash
# 推荐
make docker-reload

# 或手动
cd frontend && npm run build && cd ..
docker restart omichub-nginx

# 浏览器强制刷新
Ctrl+Shift+R
```

## 回滚策略

| 回滚场景 | 操作 |
|---|---|
| 代码回滚 | 切回上一个镜像或上一个 commit，重启容器 |
| 数据库回滚 | `docker exec omichub-web uv run alembic downgrade -1` |
| 完全回滚 | 使用备份的 `/data/omichub` 与数据库 dump 恢复 |

生产环境建议每次部署前备份：

```bash
docker exec omichub-db pg_dump -U omichub -d omichub > omichub_$(date +%F).sql
sudo rsync -aP /data/omichub/ /backup/omichub_$(date +%F)/
```
