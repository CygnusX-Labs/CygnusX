.PHONY: help dev dev-worker test lint format type-check migrate migrate-new migrate-merge migrate-rollback docker-network docker-runtime-dirs docker-fix-permissions docker-up docker-build-enrichment docker-build-deg docker-build-sandboxes docker-build-all-images docker-build-worker docker-up-worker docker-up-all docker-down docker-down-worker docker-down-all docker-logs docker-logs-worker docker-clean docker-purge docker-start docker-reload docker-dev-refresh clean init-admin init-cookies check-alembic-heads sync-knowledge

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
COMPOSE_WORKER := ./scripts/worker-compose.sh
COMPOSE_ALL    := docker compose -f deploy/docker/docker-compose.yml
DOCKER_NETWORK := omichub_net
SANDBOX_NETWORK := omichub-sandbox-net
ENRICHMENT_DOCKER_IMAGE ?= omichub-r-enrichment:v1
DEG_DOCKER_IMAGE ?= omichub-r-deg:v1
DATA_ROOT ?= /data/omichub
PUID ?= $(shell id -u)
PGID ?= $(shell id -g)
REDIS_PASSWORD ?= omichub
export REDIS_PASSWORD

docker-network: ## 创建跨栈外部网络 + 终端网络（Studio 会话网络由 Manager 动态创建）
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

docker-build-enrichment: ## 构建 GO / KEGG 富集分析 R 运行时镜像
	docker build -t $(ENRICHMENT_DOCKER_IMAGE) -f deploy/docker/Dockerfile.enrichment tool_configs/enrichments

docker-build-deg: ## 构建 DEG 差异表达分析 R 运行时镜像（DESeq2 + edgeR，支持 1v1 无重复）
	docker build -t $(DEG_DOCKER_IMAGE) -f deploy/docker/Dockerfile.deg tool_configs/deg

docker-build-sandboxes: ## 重建全部沙盒/分析运行时镜像（runtime 三件套 + 旧沙盒池 + studio base/bio + 终端全家桶，任一失败即中止）
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║  🐳 OmicHub 沙盒/分析运行时镜像全量重建（共 12 个镜像）        ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "🧪 步骤 1/5：Studio 运行时三件套（omichub-analysis core/plot/scrna）..."
	deploy/runtime-images/build.sh
	@echo "   ✅ 步骤 1/5 完成"
	@echo ""
	@echo "📦 步骤 2/5：旧沙盒池镜像（omichub/sandbox-base:latest）..."
	docker build -t omichub/sandbox-base:latest -f deploy/sandbox/Dockerfile deploy/sandbox
	@echo "   ✅ 步骤 2/5 完成"
	@echo ""
	@echo "🛠️  步骤 3/5：Studio 旧镜像（omichub-sandbox base/bio）..."
	deploy/studio/build.sh
	@echo "   ✅ 步骤 3/5 完成"
	@echo ""
	@echo "💻 步骤 4/5：终端基础镜像（omichub/sandbox-terminal:latest）..."
	docker build -t omichub/sandbox-terminal:latest tool_configs/terminal/docker/
	@echo "   ✅ 步骤 4/5 完成"
	@echo ""
	@echo "🧬 步骤 5/5：终端子镜像 6 个（rnaseq/scrna/gatk/ggplot2/assembly/metagenomics）..."
	@i=0; for t in rnaseq scrna gatk ggplot2 assembly metagenomics; do \
		i=$$((i+1)); \
		echo ""; \
		echo "   ▶ [$$i/6] 构建 omichub/sandbox-$$t:latest ..."; \
		docker build -t omichub/sandbox-$$t:latest -f tool_configs/terminal/docker/Dockerfile.$$t tool_configs/terminal/docker/ || exit 1; \
		echo "   ✅ [$$i/6] omichub/sandbox-$$t:latest 完成"; \
	done
	@echo ""
	@echo "📋 镜像清单核对："
	@ok=0; miss=0; \
	for img in omichub-analysis:core-2026.07 omichub-analysis:plot-2026.07 omichub-analysis:scrna-2026.07 \
		omichub/sandbox-base:latest omichub-sandbox:base omichub-sandbox:bio omichub/sandbox-terminal:latest \
		omichub/sandbox-rnaseq:latest omichub/sandbox-scrna:latest omichub/sandbox-gatk:latest \
		omichub/sandbox-ggplot2:latest omichub/sandbox-assembly:latest omichub/sandbox-metagenomics:latest; do \
		if docker image inspect $$img >/dev/null 2>&1; then \
			echo "   ✅ $$img"; ok=$$((ok+1)); \
		else \
			echo "   ❌ 缺失 $$img"; miss=$$((miss+1)); \
		fi; \
	done; \
	echo ""; \
	echo "=> 共 13 个镜像：就位 $$ok 个，缺失 $$miss 个"; \
	if [ $$miss -gt 0 ]; then echo "=> ⚠️  有镜像缺失，请检查上方构建日志"; exit 1; fi
	@echo "=> ✅ 全部沙盒/分析运行时镜像构建完成"

docker-build-all-images: docker-build-sandboxes docker-build-worker ## 一键重建所有镜像（沙盒/分析运行时 + 富集/DEG/Worker + 主栈/Worker compose 栈）
	$(COMPOSE_MAIN) build
	$(COMPOSE_WORKER) build
	@echo "=> ✅ 所有镜像重建完成"

docker-build-worker: docker-build-enrichment docker-build-deg ## 构建富集/DEG 运行时、通用 Worker 与系统发育 Worker 镜像
	$(COMPOSE_WORKER) build worker phylo-worker

docker-up-worker: docker-network docker-build-enrichment docker-build-deg ## 构建并启动富集/DEG 运行时、通用与系统发育 Worker 栈
	@python3 scripts/render_worker_config.py
	@set -a; . data/.worker-config.env; set +a; \
		$(MAKE) --no-print-directory docker-runtime-dirs DATA_ROOT="$$WORKER_SHARED_DATA_DIR"
	$(COMPOSE_WORKER) up -d --build worker phylo-worker

docker-up-all: docker-network ## 启动主栈 + Worker（一键全启）
	@$(MAKE) --no-print-directory docker-runtime-dirs
	$(COMPOSE_MAIN) up -d
	@$(MAKE) --no-print-directory docker-up-worker
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

docker-purge: ## [危险] 彻底清理 Docker 资源：容器+数据卷+网络+本地镜像+前端构建产物（保留宿主机 /data/omichub 数据）
	@echo "=> 停止并删除主栈与 Worker 栈容器及命名数据卷..."
	-$(COMPOSE_MAIN) down --volumes --remove-orphans 2>/dev/null
	-$(COMPOSE_WORKER) down --volumes --remove-orphans 2>/dev/null
	-docker rm -f omichub-nginx omichub-web omichub-beat omichub-flower omichub-db omichub-cache omichub-worker omichub-phylo-worker omichub-studio-egress-proxy 2>/dev/null
	-@docker ps -a --filter "name=studio-" -q | xargs -r docker rm -f 2>/dev/null
	@echo "=> 删除所有 OmicHub 数据卷（含 docker_ 前缀命名卷）..."
	-docker volume rm $$(docker volume ls -q --filter name=docker_) 2>/dev/null
	@echo "=> 删除 omichub 网络（含沙盒与 Studio 会话网络）..."
	-docker network rm $(DOCKER_NETWORK) $(SANDBOX_NETWORK) 2>/dev/null
	-@docker network ls --filter "name=studio-" -q | xargs -r docker network rm 2>/dev/null
	@echo "=> 删除本地构建镜像（主栈 / Worker / 沙盒终端 / 分析运行时 / 富集 R）..."
	-docker rmi $$(docker images --filter reference=docker-web --filter reference=docker-beat --filter reference=docker-flower --filter reference=docker-studio-egress-proxy --filter reference=omichub-worker --filter reference=omichub-phylo-worker --filter reference=omichub-r-enrichment --filter reference=omichub/sandbox-terminal --filter reference=omichub-analysis -q) 2>/dev/null
	@echo "=> 清理前端构建产物..."
	rm -rf frontend/dist
	@echo "=> Docker 资源清理完成"
	@echo "   注：数据库/用户文件/日志等持久化在宿主机 $(DATA_ROOT)（bind mount），purge 不会删除；"
	@echo "       如需一并清空数据，请手动执行: sudo rm -rf $(DATA_ROOT)"

docker-start: ## 彻底重建：清空一切 + 重建镜像 + 构建前端 + 启动全部服务
	@$(MAKE) --no-print-directory docker-purge
	@echo "=> 构建前端..."
	cd frontend && npm run build
	@echo "=> 重建 Docker 镜像..."
	$(COMPOSE_MAIN) build --no-cache
	$(COMPOSE_WORKER) build --no-cache
	@$(MAKE) --no-print-directory docker-build-enrichment
	@$(MAKE) --no-print-directory docker-build-deg
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

runtime-images-build: ## 构建独立分析运行时镜像（core / plot / scrna）
	deploy/runtime-images/build.sh

docker-reload: docker-network ## 重新构建前端并刷新主栈 + Worker (开发用)
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║  🚀 OmicHub 开发环境热重载                                    ║"
	@echo "║     重新构建前端 + 重启服务 + 同步知识库                      ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@$(MAKE) --no-print-directory docker-runtime-dirs
	@echo ""
	@echo "📦 步骤 1/8：清理残留容器，避免旧容器占用端口或挂载..."
	-@docker ps -a --filter "name=omichub-" -q | xargs -r docker rm -f 2>/dev/null
	-@docker ps -a --filter "name=studio-" -q | xargs -r docker rm -f 2>/dev/null
	@echo ""
	@echo "🐳 步骤 2/8：构建终端沙盒镜像（已存在则跳过，删除镜像后自动重建）..."
	@docker image inspect omichub/sandbox-terminal:latest >/dev/null 2>&1 && \
		echo "   ⏭️  omichub/sandbox-terminal:latest 已存在，跳过构建" || \
		docker build -t omichub/sandbox-terminal:latest tool_configs/terminal/docker/
	@echo ""
	@echo "🧪 步骤 3/8：构建 Studio 运行时镜像（core/plot/scrna 均已存在则跳过）..."
	@if docker image inspect omichub-analysis:core-2026.07 >/dev/null 2>&1 && \
	    docker image inspect omichub-analysis:plot-2026.07 >/dev/null 2>&1 && \
	    docker image inspect omichub-analysis:scrna-2026.07 >/dev/null 2>&1; then \
		echo "   ⏭️  omichub-analysis 三个运行时镜像均已存在，跳过构建"; \
	else \
		deploy/runtime-images/build.sh; \
	fi
	@echo ""
	@echo "🧬 步骤 4/8：构建 GO / KEGG 富集 R 运行时镜像（已存在则跳过）..."
	@docker image inspect $(ENRICHMENT_DOCKER_IMAGE) >/dev/null 2>&1 && \
		echo "   ⏭️  $(ENRICHMENT_DOCKER_IMAGE) 已存在，跳过构建" || \
		$(MAKE) --no-print-directory docker-build-enrichment
	@echo ""
	@echo "📊 构建 DEG 差异表达分析 R 运行时镜像（已存在则跳过）..."
	@docker image inspect $(DEG_DOCKER_IMAGE) >/dev/null 2>&1 && \
		echo "   ⏭️  $(DEG_DOCKER_IMAGE) 已存在，跳过构建" || \
		$(MAKE) --no-print-directory docker-build-deg
	@echo ""
	@echo "⚡ 步骤 5/8：重新构建前端生产包（vite build）..."
	cd frontend && npm run build
	@echo ""
	@echo "🌐 步骤 6/8：重新构建并启动主栈服务（web / db / redis / nginx / beat / flower）..."
	$(COMPOSE_MAIN) up -d --build
	@echo ""
	@echo "🔧 步骤 7/8：构建并启动通用与系统发育 Worker 计算栈..."
	$(COMPOSE_WORKER) up -d --build worker phylo-worker
	@echo ""
	@echo "🗄️  步骤 8/8：检查数据库迁移状态并同步知识库..."
	@$(MAKE) --no-print-directory check-alembic-heads
	@$(MAKE) --no-print-directory sync-knowledge
	@echo ""
	@echo "✅ 热重载完成！访问地址：http://localhost:8888"
	@echo ""

docker-dev-refresh: ## 轻量热刷新：前端 build + 重启 web/beat/nginx + 跑迁移（日常改代码/YAML 用，秒级，不重建镜像）
	@echo ""
	@echo "⚡ 步骤 1/3：前端生产包构建（vite build；nginx 直接读挂载的 dist）..."
	cd frontend && npm run build
	@echo ""
	@echo "🔄 步骤 2/3：重启 web / beat / nginx（src/data/alembic/flows/tool_configs 均为 bind mount，重启即生效；"
	@echo "   vite 重建 dist 后旧 nginx 进程持有旧目录句柄，必须一并重启）..."
	$(COMPOSE_MAIN) restart web beat nginx
	@echo ""
	@echo "🗄️  步骤 3/3：应用数据库迁移（web entrypoint 启动时也会自动执行，这里确保即时生效）..."
	@docker exec omichub-web alembic upgrade head
	@echo ""
	@echo "✅ 刷新完成！访问地址：http://localhost:8888"
	@echo "   提示：仅 pyproject.toml / uv.lock / Dockerfile 变更时才需要 make docker-reload（--build 重建镜像）；"
	@echo "        data/ai/*.yaml 与提示词按 mtime/调用热重载，改完刷新页面即可，无需执行本命令。"
	@echo ""

sync-knowledge: ## 将 docs/knowledge/*.md 同步到数据库（开发/本地文件编辑后使用）
	@echo ""
	@echo "📚 同步知识库：将 docs/knowledge/*.md 文件内容同步到数据库..."
	@echo "   （说明：知识库以数据库为权威源，直接改 .md 文件后需要此步骤网页才生效）"
	@docker exec omichub-web python scripts/sync_knowledge_from_files.py \
		--meta-yaml docs/knowledge/meta.yaml \
		--auto-admin

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
