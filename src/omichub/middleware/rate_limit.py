"""限流中间件 - 基于 Redis 滑动窗口"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """简单限流 - 每分钟每 IP 最多 100 次请求"""

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        # TODO: 接入 Redis 实现分布式限流
        # 当前骨架阶段直接放行
        return await call_next(request)
