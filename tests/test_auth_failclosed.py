"""mcp_perm 鉴权 fail-closed + async 保真单元测试。

覆盖：admin 模式 AuthContext 缺失拒绝；tool 模式放行；superuser 直通；
普通用户缺码拒绝/有码放行；async 工具 wrapper 保真（scope 注入在协程内生效）。
"""

import pytest

from service_mcp.auth.context import AuthContext, PermScope, _auth_context
from service_mcp.auth.decorator import mcp_perm
from service_mcp.models.common import UtilResponse


@mcp_perm("01", "03")  # SM_010103 产品新增
async def _async_tool(payload: str = "ok") -> dict:
    from service_mcp.auth.context import get_current_scope

    scope = get_current_scope()
    return {"result": payload, "scope": getattr(scope, "data_scope", None)}


@mcp_perm("07", "07")  # SM_010707 配置管理
def _sync_tool() -> dict:
    return {"result": "sync"}


def _enter_ctx(ctx: AuthContext | None):
    return _auth_context.set(ctx)


def _exit_ctx(token) -> None:
    _auth_context.reset(token)


class TestAdminModeFailClosed:
    @pytest.fixture(autouse=True)
    def _admin_mode(self, monkeypatch):
        monkeypatch.setenv("MCP_AUTH_MODE", "admin")

    async def test_async_tool_denied_without_context(self):
        out = await _async_tool(payload="x")
        assert isinstance(out, UtilResponse)
        assert "缺少认证上下文" in (out.message or "")

    def test_sync_tool_denied_without_context(self):
        out = _sync_tool()
        assert isinstance(out, UtilResponse)
        assert "缺少认证上下文" in (out.message or "")

    async def test_superuser_bypasses(self):
        token = _enter_ctx(AuthContext(user_id=1, username="su", is_superuser=True))
        try:
            out = await _async_tool(payload="su")
            assert out == {"result": "su", "scope": None}
        finally:
            _exit_ctx(token)

    async def test_normal_user_missing_scope_denied(self):
        token = _enter_ctx(AuthContext(user_id=2, username="u", permissions={}))
        try:
            out = await _async_tool(payload="x")
            assert isinstance(out, UtilResponse)
            assert "缺少权限" in (out.message or "")
        finally:
            _exit_ctx(token)

    async def test_async_tool_scope_injected_in_coroutine(self):
        """async 保真回归：wrapper 必须保持 async，_current_perm_scope 在协程体内可见。"""
        token = _enter_ctx(
            AuthContext(
                user_id=3,
                username="u3",
                permissions={"SM_010103": PermScope(data_scope="OWN")},
            )
        )
        try:
            out = await _async_tool(payload="ok3")
            assert out == {"result": "ok3", "scope": "OWN"}
        finally:
            _exit_ctx(token)


class TestToolModeKeepsLegacyAllow:
    @pytest.fixture(autouse=True)
    def _tool_mode(self, monkeypatch):
        monkeypatch.delenv("MCP_AUTH_MODE", raising=False)

    async def test_async_tool_allowed_without_context(self):
        out = await _async_tool(payload="tool")
        assert out == {"result": "tool", "scope": None}

    def test_sync_tool_allowed_without_context(self):
        assert _sync_tool() == {"result": "sync"}
