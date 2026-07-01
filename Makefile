.PHONY: help dev dev-worker test lint format type-check migrate migrate-new docker-network docker-up docker-up-worker docker-up-all docker-down docker-down-worker docker-down-all docker-logs docker-logs-worker docker-clean docker-purge clean init-admin init-cookies

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

# ===== Docker Compose 编排（主栈 + 独立 Worker 栈，单机逻辑解耦）=====
COMPOSE_MAIN   := docker compose -f deploy/docker/docker-compose.yml
COMPOSE_WORKER := docker compose -f deploy/docker/docker-compose.worker.yml
COMPOSE_ALL    := docker compose -f deploy/docker/docker-compose.yml -f deploy/docker/docker-compose.worker.yml
DOCKER_NETWORK := omichub_net

docker-network: ## 创建跨栈外部网络 omichub_net（幂等）
	@docker network create $(DOCKER_NETWORK) 2>/dev/null || true

docker-up: docker-network ## 启动主栈 (web/db/redis/nginx/beat/flower)
	$(COMPOSE_MAIN) up -d

docker-up-worker: docker-network ## 启动独立计算节点 Worker 栈
	$(COMPOSE_WORKER) up -d

docker-up-all: docker-network ## 启动主栈 + Worker（一键全启）
	$(COMPOSE_MAIN) up -d
	$(COMPOSE_WORKER) up -d

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

docker-purge: ## [危险] 彻底清理：容器+数据卷+网络+本地镜像（不可逆，重置到干净状态）
	$(COMPOSE_ALL) down -v --rmi local --remove-orphans
	@docker network rm $(DOCKER_NETWORK) 2>/dev/null || true

frontend-install: ## 安装前端依赖
	cd frontend && npm install

frontend-dev: ## 启动前端开发服务器
	cd frontend && npm run dev

frontend-build: ## 构建前端生产版本
	cd frontend && npm run build

docker-reload: docker-network ## 重新构建前端并刷新主栈 + Worker (开发用)
	cd frontend && npm run build
	$(COMPOSE_MAIN) restart nginx
	$(COMPOSE_MAIN) restart web   # web 关闭了 --reload，改后端代码需手动 restart 才生效
	$(COMPOSE_MAIN) up -d
	$(COMPOSE_WORKER) up -d

init-admin: ## 初始化管理员账号 (首次部署使用)
	uv run python scripts/init_admin.py

init-cookies: ## 初始化默认饼干定价策略
	uv run python scripts/init_cookies.py

clean: ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type f -name "*.pyc" -delete; \
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
