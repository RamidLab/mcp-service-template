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


_auth_context: contextvars.ContextVar[AuthContext | None] = contextvars.ContextVar(
    "auth_context", default=None
)
_current_perm_scope: contextvars.ContextVar[PermScope | None] = contextvars.ContextVar(
    "current_perm_scope", default=None
)


def get_auth_context() -> AuthContext | None:
    return _auth_context.get()


def get_current_scope() -> PermScope | None:
    return _current_perm_scope.get()
