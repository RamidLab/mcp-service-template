from __future__ import annotations

import inspect
import os
from functools import wraps

from service_mcp.auth.context import _auth_context, _current_perm_scope
from service_mcp.models.common import UtilResponse
from service_mcp.utils.enums import Errcode


def _auth_context_missing_response() -> UtilResponse:
    """admin 模式下 AuthContext 缺失的统一拒绝响应（fail-closed）。"""
    return UtilResponse(
        code=Errcode.AUTH_FAILED,
        message="缺少认证上下文（AuthContext 未注入；后台任务需实现身份快照恢复后再启用）",
        data=None,
    )


def mcp_perm(resource: str, action: str):
    """声明工具的资源码 + 操作码，自动拼装 SM_ 权限码并做运行时校验。

    Args:
        resource: 资源码 (01=产品, 02=产品价格, 07=配置, 08=审计)
        action:   操作码 (01=list, 02=detail, 03=create, 04=update, 06=delete, 07=manage, 08=read)
    """
    perm_code = f"SM_01{resource}{action}"

    def decorator(func):
        func._mcp_perm_code = perm_code
        func._mcp_resource = resource
        func._mcp_action = action

        if inspect.iscoroutinefunction(func):
            # async 工具：wrapper 保持 async（否则 FastMCP 误判为同步函数，
            # 后台任务（task=True）校验会拒绝，且 async 体内读取 scope 失效——
            # 同步 wrapper 在线程 set/reset，协程体在事件循环执行时读到 None，OWN 数据范围静默失效）
            @wraps(func)
            async def wrapper(*args, **kwargs):
                ctx = _auth_context.get()
                if ctx is None:
                    # fail-closed：admin 模式必须有 AuthContext（HTTP 中间件注入）；
                    # 后台任务 worker 未恢复 AuthContext 时拒绝执行；
                    # tool 模式（MCP_AUTH_MODE=tool）无鉴权全量可见。
                    if os.getenv("MCP_AUTH_MODE", "tool") == "admin":
                        return _auth_context_missing_response()
                    return await func(*args, **kwargs)
                if ctx.is_superuser:
                    return await func(*args, **kwargs)

                scope = ctx.permissions.get(perm_code)
                if scope is None:
                    return UtilResponse(
                        code=Errcode.AUTH_INSUFFICIENT_SCOPE,
                        message=f"缺少权限: {perm_code}",
                        data=None,
                    )

                token = _current_perm_scope.set(scope)
                try:
                    return await func(*args, **kwargs)
                finally:
                    _current_perm_scope.reset(token)
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                ctx = _auth_context.get()
                if ctx is None:
                    # 与 async 分支一致：admin 模式 fail-closed，tool 模式放行
                    if os.getenv("MCP_AUTH_MODE", "tool") == "admin":
                        return _auth_context_missing_response()
                    return func(*args, **kwargs)
                if ctx.is_superuser:
                    return func(*args, **kwargs)

                scope = ctx.permissions.get(perm_code)
                if scope is None:
                    return UtilResponse(
                        code=Errcode.AUTH_INSUFFICIENT_SCOPE,
                        message=f"缺少权限: {perm_code}",
                        data=None,
                    )

                token = _current_perm_scope.set(scope)
                try:
                    return func(*args, **kwargs)
                finally:
                    _current_perm_scope.reset(token)

        # Python 3.14 的 wraps 不再复制 __annotations__（改用 __annotate__），
        # 而 __annotate__ 不反映运行时注入的注解；此处显式继承保证签名完整
        wrapper.__annotations__ = func.__annotations__
        return wrapper

    return decorator
