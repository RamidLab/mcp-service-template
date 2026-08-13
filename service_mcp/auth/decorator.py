from __future__ import annotations

from functools import wraps

from service_mcp.auth.context import _auth_context, _current_perm_scope
from service_mcp.models.common import UtilResponse
from service_mcp.utils.enums import Errcode


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

        @wraps(func)
        def wrapper(*args, **kwargs):
            ctx = _auth_context.get()
            if ctx is None or ctx.is_superuser:
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
