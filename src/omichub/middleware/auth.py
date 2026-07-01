"""JWT 认证中间件 - 全局请求拦截校验"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from omichub.core.security import decode_token

# 不需要认证的路径前缀/精确匹配
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/setup-required",
        "/api/v1/auth/setup",
        # 站点级公开配置：登录页未登录即需读取
        "/api/v1/site-settings",   # 注册开关（关闭时登录页拦截注册按钮）
        "/api/v1/site-content",    # 首页文案 + 注册提示文案（YAML 驱动）
    }
)


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT 认证中间件 - 校验 Authorization 头并注入 user_id 到 request.state"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 公开路径直接放行
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # WebSocket 连接由端点内自行处理
        if request.scope["type"] == "websocket":
            return await call_next(request)

        # 静态资源 / 文档放行
        if path.startswith(("/docs", "/redoc", "/assets")):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response(
                status_code=401,
                content='{"detail":"未提供认证令牌"}',
                media_type="application/json",
            )

        token = auth_header.removeprefix("Bearer ")
        payload = decode_token(token)
        if payload is None:
            return Response(
                status_code=401,
                content='{"detail":"令牌无效或已过期"}',
                media_type="application/json",
            )

        # 将用户 ID 注入 request state，供后续依赖使用
        request.state.user_id = payload.get("sub")

        return await call_next(request)
