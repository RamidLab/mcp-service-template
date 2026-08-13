from service_mcp.auth.config import AuthConfig
from service_mcp.auth.context import (
    AuthContext,
    PermScope,
    get_auth_context,
    get_current_scope,
)
from service_mcp.auth.decorator import mcp_perm
from service_mcp.auth.discovery import get_all_permissions
from service_mcp.auth.middleware import JWTAuthMiddleware


__all__ = [
    "AuthConfig",
    "AuthContext",
    "JWTAuthMiddleware",
    "PermScope",
    "get_all_permissions",
    "get_auth_context",
    "get_current_scope",
    "mcp_perm",
]
