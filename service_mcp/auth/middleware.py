from __future__ import annotations

import aiohttp
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from service_mcp.auth.config import AuthConfig
from service_mcp.auth.context import AuthContext, PermScope, _auth_context


class JWTAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, config: AuthConfig):
        super().__init__(app)
        self.config = config

    async def dispatch(self, request, call_next):
        if self.config.mode != "admin":
            return await call_next(request)

        path = request.url.path.rstrip("/")
        if path in self.config.bypass_paths:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                {"code": -414001, "message": "未提供认证令牌", "data": None},
                status_code=401,
            )

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(
                    self.config.auth_api_url,
                    headers={"Authorization": auth_header},
                ) as resp:
                    status = resp.status
                    data = await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return JSONResponse(
                {"code": -501003, "message": "认证服务不可用", "data": None},
                status_code=502,
            )

        if status != 200 or data.get("code") != 0:
            return JSONResponse(
                {
                    "code": data.get("code", -414001),
                    "message": data.get("message", "认证失败"),
                    "data": None,
                },
                status_code=status,
            )

        user = data["data"]

        # 如果后端返回了新 token，使用新 token 更新请求头
        new_access_token = user.get("new_access_token")
        if new_access_token:
            auth_header = f"Bearer {new_access_token}"
            # 将新 token 存储到 request.state 供后续使用
            request.state.new_access_token = new_access_token

        perms = {code: PermScope(**v) for code, v in user["permissions"].items()}
        ctx = AuthContext(
            user_id=user["user_id"],
            username=user["username"],
            roles=user["roles"],
            permissions=perms,
            is_superuser=user["is_superuser"],
            is_staff=user["is_staff"],
            access_token=auth_header.replace("Bearer ", "") if auth_header else None,
        )
        token = _auth_context.set(ctx)
        try:
            return await call_next(request)
        finally:
            _auth_context.reset(token)
