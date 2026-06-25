"""FastAPI 应用入口"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from omichub.api.v1.router import api_router
from omichub.core.config import get_settings
from omichub.core.exceptions import OmicHubError
from omichub.core.logging import setup_logging
from omichub.middleware.auth import AuthMiddleware
from omichub.middleware.cookie import CookieRequiredMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动与关闭"""
    setup_logging()
    from loguru import logger

    settings = get_settings()
    logger.info(f"启动 {settings.app_name} (env={settings.app_env})")

    # 启动时初始化连接（数据库不可用时降级运行，便于骨架阶段独立启动）
    from omichub.infrastructure.database.session import init_db

    try:
        await init_db()
        logger.info("数据库连接已就绪")
    except Exception as e:
        logger.warning(f"数据库未就绪，降级运行: {e}")

    yield

    # 关闭时清理
    from omichub.infrastructure.database.session import close_db

    await close_db()
    logger.info("应用已关闭")


def create_app() -> FastAPI:
    """FastAPI 应用工厂"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="私有化多组学分析平台",
        version="0.1.0",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
        lifespan=lifespan,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # JWT 认证中间件（全局拦截，公开路径在 PUBLIC_PATHS 中配置）
    app.add_middleware(AuthMiddleware)

    # 饼干消费拦截中间件（消费类路由的账户状态守卫）
    app.add_middleware(CookieRequiredMiddleware)

    # 全局异常处理
    @app.exception_handler(OmicHubError)
    async def omichub_error_handler(request: Request, exc: OmicHubError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # 注册路由
    app.include_router(api_router, prefix="/api/v1")

    # 开发模式下提供顶层重定向，便于直接访问 uvicorn 时不因缺少 /api/v1 前缀而 404
    if settings.app_debug:

        @app.get("/flows", include_in_schema=False)
        async def _redirect_flows_root(request: Request) -> RedirectResponse:
            return RedirectResponse(url=f"/api/v1/flows{request.query_params}")

        @app.get("/flows/{path:path}", include_in_schema=False)
        async def _redirect_flows_path(request: Request, path: str) -> RedirectResponse:
            return RedirectResponse(url=f"/api/v1/flows/{path}{request.query_params}")

    # 健康检查
    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
