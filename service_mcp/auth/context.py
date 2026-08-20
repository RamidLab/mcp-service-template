from __future__ import annotations

import contextvars
from dataclasses import dataclass, field


@dataclass
class PermScope:
    data_scope: str = "ALL"
    custom: list[dict] = field(default_factory=list)


@dataclass
class AuthContext:
    user_id: int = 0
    username: str = ""
    roles: list[str] = field(default_factory=list)
    permissions: dict[str, PermScope] = field(default_factory=dict)
    is_superuser: bool = False
    is_staff: bool = False
    access_token: str | None = None  # JWT token，用于调用后端 API


_auth_context: contextvars.ContextVar[AuthContext | None] = contextvars.ContextVar(
    "auth_context", default=None
)
_current_perm_scope: contextvars.ContextVar[PermScope | None] = contextvars.ContextVar(
    "current_perm_scope", default=None
)


def get_auth_context() -> AuthContext | None:
    return _auth_context.get()


def set_auth_context(ctx: AuthContext | None) -> None:
    """注入/清除当前请求的认证上下文（测试与包模式宿主使用）。"""
    _auth_context.set(ctx)


def get_current_scope() -> PermScope | None:
    return _current_perm_scope.get()


def current_owner() -> int | None:
    """当前操作者归属：admin 模式取后端用户 ID；无鉴权（tool）返回 None。"""
    ctx = _auth_context.get()
    if ctx is None:
        return None
    return ctx.user_id


def visible_owners() -> set[int] | None:
    """当前可见的归属集合；None 表示全量可见。

    - 无鉴权调用：全量（None，不隔离）
    - 普通用户：仅自己的数据（{user_id}）
    - superuser：全量
    """
    ctx = _auth_context.get()
    if ctx is None or ctx.is_superuser:
        return None
    return {ctx.user_id}
