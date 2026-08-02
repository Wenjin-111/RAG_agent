import time
import logging

from app.common.security.context import UserContext

logger = logging.getLogger("argus.access")


class LoggingMiddleware:
    """Pure-ASGI access log middleware.

    不用 BaseHTTPMiddleware：其 call_next 在子 task 中运行路由处理，
    子 task 内的 contextvar 修改不会反向传播，导致 UserContext 读不到
    （userId 恒为 None）。纯 ASGI 直接 await self.app 在同一 task 中执行。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            user = UserContext.get()
            user_id = user.user_id if user else None
            logger.info(
                "%s %s -> %s (%dms) userId=%s",
                scope["method"],
                scope["path"],
                status_code,
                elapsed_ms,
                user_id,
            )
