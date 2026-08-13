from collections.abc import Callable
from typing import Any

from prefab_ui.actions.mcp import CallTool as _OriginalCallTool
from prefab_ui.actions.mcp import get_tool_resolver

from service_mcp.tools import is_global_tool_name


class CallTool(_OriginalCallTool):
    """
    重写 CallTool 类，确保在序列化时直接使用工具名称，不附加任何 App 的命名空间前缀
    """

    def __init__(self, tool: str | Callable[..., Any], **kwargs):
        super().__init__(tool, **kwargs)

    def _serialize_with_resolver(self, handler: Any) -> dict[str, Any]:
        raw_dict: dict[str, Any] = handler(self)
        tool_name = self.tool

        if isinstance(tool_name, str) and is_global_tool_name(tool_name):
            raw_dict["tool"] = tool_name
        else:
            # App 私有工具：走 resolver 加哈希
            resolver = get_tool_resolver()
            if resolver is not None:
                resolved = resolver(tool_name)
                raw_dict["tool"] = resolved.name
                if resolved.unwrap_result:
                    raw_dict["unwrapResult"] = True
            else:
                raw_dict["tool"] = tool_name

        return {k: v for k, v in raw_dict.items() if v is not None}
