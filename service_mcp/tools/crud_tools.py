"""CRUD 工具 — 由 crud_factory 注册表统一生成 add/update/delete 工具。"""

from service_mcp.tools.crud_factory import register_crud_tools


# 工具由注册表统一生成，__all__ 为动态构造
__all__ = register_crud_tools(globals())  # noqa: PLE0605
