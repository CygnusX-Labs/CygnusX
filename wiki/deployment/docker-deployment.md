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

## Worker 镜像与交互终端

Worker 镜像 `omichub-worker:dev` 除运行 Celery、Snakemake、Micromamba 外，还包含：

- `btop`：查看容器内资源使用情况。
- `zsh`、Oh My Zsh、Oh My Posh：计算节点的交互式终端体验。
- `omichub` 运行账户（UID/GID `1000`，默认 shell 为 Zsh）。

镜像入口会在启动 Worker 时准备共享盘目录，并将进程降权为 `omichub`。该账户的 HOME 是 `/tmp/omichub-home`，因此 `btop`、Zsh 历史与 Snakemake logger 都有可写的用户目录。Snakemake logger 不会再因 UID `1000` 缺少 passwd 条目而出现 `getpwuid(): uid not found: 1000`。

```bash
# 修改 deploy/docker/Dockerfile.worker 或 worker-entrypoint.sh 后重建
make docker-build-worker

# 进入正在运行的计算 Worker
docker exec -it omichub-worker zsh

# 本地检查镜像；交互式裸 bash 会自动切换至 zsh
docker run --rm -it omichub-worker:dev bash
```

入口脚本只会将交互式、无额外参数的 `bash` 切换为 Zsh；`bash -c '...'`、`bash -ic '...'` 等脚本调用保持 Bash 语义，Compose 中的 Celery `command` 也不会被修改。
