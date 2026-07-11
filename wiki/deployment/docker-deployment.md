# Docker 部署

OmicHub 控制面与计算面拆分为两个独立 Docker Compose 栈，通过外部网络 `omichub_net` 共享 Redis，并挂载同一 `/data/omichub`。

## 服务组成

| 栈 | 服务 | 说明 |
|---|---|---|
| 主栈 `docker-compose.yml` | web / db / redis / nginx / beat / flower | Web 控制面 + 定时器 |
| Worker 栈 `docker-compose.worker.yml` | worker | Celery 计算节点，可水平扩展 |

## 首次部署

```bash
# 准备数据目录
sudo mkdir -p /data/omichub
sudo chown $USER:$USER /data/omichub

# 配置 .env（JWT、Redis、AI 密钥等）

# 构建前端
cd frontend && npm install && npm run build && cd ..

# 启动
make docker-up          # 主栈
make docker-up-worker   # Worker 栈

# 初始化
docker exec omichub-web uv run alembic upgrade head
docker exec omichub-web uv run python scripts/init_admin.py
docker exec omichub-web uv run python scripts/init_cookies.py
```

## 生产部署

```bash
docker compose -f deploy/docker/docker-compose.yml \
               -f deploy/docker/docker-compose.prod.yml up -d

docker compose -f deploy/docker/docker-compose.worker.yml \
               --scale worker=2 up -d
```

prod override 关闭 DB/Redis 宿主端口、Flower 副本为 0、使用 4 uvicorn worker。
