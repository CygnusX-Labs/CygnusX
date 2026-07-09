.PHONY: help dev dev-worker test lint format type-check migrate migrate-new migrate-merge migrate-rollback docker-network docker-runtime-dirs docker-fix-permissions docker-up docker-up-worker docker-up-all docker-down docker-down-worker docker-down-all docker-logs docker-logs-worker docker-clean docker-purge docker-start clean init-admin init-cookies check-alembic-heads

help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## 启动后端开发服务器
	uv run uvicorn omichub.main:app --reload --host 0.0.0.0 --port 8000

dev-worker: ## 启动 Celery Worker
	uv run celery -A omichub.infrastructure.celery_app.celery worker --loglevel=info

dev-beat: ## 启动 Celery Beat
	uv run celery -A omichub.infrastructure.celery_app.celery beat --loglevel=info

dev-flower: ## 启动 Flower 监控
	uv run celery -A omichub.infrastructure.celery_app.celery flower --port=5555

test: ## 运行测试
	uv run pytest tests/ -v

test-cov: ## 运行测试并生成覆盖率报告
	uv run pytest tests/ --cov=src/omichub --cov-report=term-missing --cov-report=html

lint: ## 代码检查
	uv run ruff check src/ tests/

format: ## 代码格式化
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

type-check: ## 类型检查
	uv run mypy src/omichub/

migrate: ## 执行数据库迁移
	uv run alembic upgrade head

migrate-new: ## 创建新迁移 (用法: make migrate-new m="migration name")
	uv run alembic revision --autogenerate -m "$(m)"

migrate-rollback: ## 回滚上一个迁移
	uv run alembic downgrade -1

migrate-merge: ## 自动合并 Alembic 多分支 (Multiple Heads 修复)
	@echo "=> 正在合并 Alembic 多分支..."
	uv run alembic merge heads -m "auto-merge parallel branches"
	uv run alembic upgrade head
	@echo "=> ✅ 多分支合并完成，数据库已更新至最新版本。"

# ===== Docker Compose 编排（主栈 + 独立 Worker 栈，单机逻辑解耦）=====
COMPOSE_MAIN   := docker compose -f deploy/docker/docker-compose.yml
COMPOSE_WORKER := docker compose -f deploy/docker/docker-compose.worker.yml
COMPOSE_ALL    := docker compose -f deploy/docker/docker-compose.yml -f deploy/docker/docker-compose.worker.yml
DOCKER_NETWORK := omichub_net
SANDBOX_NETWORK := omichub-sandbox-net
DATA_ROOT ?= /data/omichub
PUID ?= $(shell id -u)
PGID ?= $(shell id -g)

docker-network: ## 创建跨栈外部网络 omichub_net + 终端沙盒网络（幂等）
	@docker network create $(DOCKER_NETWORK) 2>/dev/null || true
	@docker network create $(SANDBOX_NETWORK) 2>/dev/null || true

docker-runtime-dirs: ## 准备关键运行目录与非 root 容器写入权限（docker-up/reload 自动执行）
	@echo "=> 准备运行目录权限..."
	@docker run --rm -v $(DATA_ROOT):/data-root python:3.11-slim sh -c 'mkdir -p /data-root/logs/app /data-root/logs/celery/tasks /data-root/logs/nginx /data-root/logs/snakemake /data-root/users /data-root/uploads /data-root/.tmp /data-root/.conda_envs /data-root/omichub_data/_pgdata /data-root/omichub_data/_redis && chown -R $(PUID):$(PGID) /data-root/logs/app /data-root/logs/celery /data-root/logs/snakemake /data-root/uploads /data-root/.tmp /data-root/.conda_envs && chown $(PUID):$(PGID) /data-root/users'

docker-fix-permissions: ## 手动修复 /data/omichub 权限事故（登录 500 / PermissionError 时使用）
	@echo "=> 修复 /data/omichub 非 root 服务写入权限..."
	@docker run --rm -v $(DATA_ROOT):/data-root python:3.11-slim sh -c 'mkdir -p /data-root/logs/app /data-root/logs/celery/tasks /data-root/logs/nginx /data-root/logs/snakemake /data-root/users /data-root/uploads /data-root/.tmp /data-root/.conda_envs /data-root/omichub_data/_pgdata /data-root/omichub_data/_redis && chown -R $(PUID):$(PGID) /data-root/logs/app /data-root/logs/celery /data-root/logs/snakemake /data-root/users /data-root/uploads /data-root/.tmp /data-root/.conda_envs'
	@echo "=> 权限修复完成。建议执行: docker restart omichub-web omichub-worker omichub-beat"

docker-up: docker-network ## 启动主栈 (web/db/redis/nginx/beat/flower)
	@$(MAKE) --no-print-directory docker-runtime-dirs
	$(COMPOSE_MAIN) up -d
	@$(MAKE) --no-print-directory check-alembic-heads

docker-up-worker: docker-network ## 启动独立计算节点 Worker 栈
	@$(MAKE) --no-print-directory docker-runtime-dirs
	$(COMPOSE_WORKER) up -d

docker-up-all: docker-network ## 启动主栈 + Worker（一键全启）
	@$(MAKE) --no-print-directory docker-runtime-dirs
	$(COMPOSE_MAIN) up -d
	$(COMPOSE_WORKER) up -d
	@$(MAKE) --no-print-directory check-alembic-heads

docker-down: ## 停止主栈
	$(COMPOSE_MAIN) down

docker-down-worker: ## 停止 Worker 栈
	$(COMPOSE_WORKER) down

docker-down-all: ## 停止主栈 + Worker
	$(COMPOSE_ALL) down

docker-logs: ## 查看主栈日志
	$(COMPOSE_MAIN) logs -f

docker-logs-worker: ## 查看 Worker 日志
	$(COMPOSE_WORKER) logs -f

docker-clean: ## 清理容器与网络（保留数据卷，不删镜像）
	$(COMPOSE_ALL) down --remove-orphans

docker-purge: ## [危险] 彻底清理：容器+数据卷+网络+本地镜像+前端构建产物（不可逆，重置到干净状态）
	@echo "=> 停止并删除所有容器及命名数据卷..."
	-$(COMPOSE_ALL) down --volumes --remove-orphans 2>/dev/null
	-docker rm -f omichub-nginx omichub-web omichub-beat omichub-flower omichub-db omichub-cache omichub-worker 2>/dev/null
	@echo "=> 删除所有 OmicHub 数据卷（含 docker_ 前缀命名卷）..."
	-docker volume rm $$(docker volume ls -q --filter name=docker_) 2>/dev/null
	@echo "=> 删除 omichub 网络..."
	-docker network rm $(DOCKER_NETWORK) 2>/dev/null
	@echo "=> 删除本地构建镜像..."
	-docker rmi $$(docker images --filter reference=docker-web --filter reference=docker-beat --filter reference=docker-flower --filter reference=docker-worker -q) 2>/dev/null
	@echo "=> 清理前端构建产物..."
	rm -rf frontend/dist
	@echo "=> 清理完成"

docker-start: ## 彻底重建：清空一切 + 重建镜像 + 构建前端 + 启动全部服务
	@$(MAKE) --no-print-directory docker-purge
	@echo "=> 构建前端..."
	cd frontend && npm run build
	@echo "=> 重建 Docker 镜像..."
	$(COMPOSE_MAIN) build --no-cache
	$(COMPOSE_WORKER) build --no-cache
	@echo "=> 启动全部服务..."
	@$(MAKE) --no-print-directory docker-network
	@$(MAKE) --no-print-directory docker-runtime-dirs
	$(COMPOSE_MAIN) up -d
	$(COMPOSE_WORKER) up -d
	@$(MAKE) --no-print-directory check-alembic-heads

frontend-install: ## 安装前端依赖
	cd frontend && npm install

frontend-dev: ## 启动前端开发服务器
	cd frontend && npm run dev

frontend-build: ## 构建前端生产版本
	cd frontend && npm run build

docker-reload: docker-network ## 重新构建前端并刷新主栈 + Worker (开发用)
	@$(MAKE) --no-print-directory docker-runtime-dirs
	@echo "=> 清理残留容器..."
	-@docker ps -a --filter "name=omichub-" -q | xargs -r docker rm -f 2>/dev/null
	@echo "=> 构建终端沙盒镜像..."
	-docker build -t omichub/sandbox-terminal:latest tool_configs/terminal/docker/
	cd frontend && npm run build
	$(COMPOSE_MAIN) up -d
	$(COMPOSE_WORKER) up -d
	@$(MAKE) --no-print-directory check-alembic-heads

init-admin: ## 初始化管理员账号 (首次部署使用)
	uv run python scripts/init_admin.py

init-cookies: ## 初始化默认饼干定价策略
	uv run python scripts/init_cookies.py

check-alembic-heads: ## 检测 Alembic 迁移是否存在多分支 (Multiple Heads)
	@echo "=> 🐱 正在检查 Alembic 数据库迁移状态..."
	@sleep 3  # 等待 web 容器就绪
	@HEAD_COUNT=$$(docker exec omichub-web alembic heads 2>/dev/null | grep -c '(head)' || echo 0); \
	if [ "$$HEAD_COUNT" -gt 1 ]; then \
		echo ""; \
		echo "====================================================================="; \
		echo "  🚨 [警告] Alembic 存在多个分支 (Multiple Heads)！"; \
		echo "  ⚠️  数据库处于分叉状态，登录等接口可能触发 500 错误。"; \
		echo ""; \
		echo "  🛠️  修复命令（直接复制执行）："; \
		echo ""; \
		echo "    make migrate-merge"; \
		echo ""; \
		echo "  或手动分步："; \
		echo "    docker exec omichub-web alembic merge heads -m \"merge parallel branches\""; \
		echo "    docker exec omichub-web alembic upgrade head"; \
		echo "====================================================================="; \
		echo ""; \
	else \
		echo "=> ✅ 数据库版本树正常，未发现分叉。"; \
	fi

check-migrations: ## 静态检查 Alembic 迁移链完整性（不依赖数据库）
	@uv run python scripts/check_migrations.py

clean: ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type f -name "*.pyc" -delete; \
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
