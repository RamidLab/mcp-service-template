from collections.abc import Callable


_GLOBAL_TOOL_NAMES: set[str] = set()


def global_tool(fn: Callable) -> Callable:
    """标记函数为全局共享工具"""
    _GLOBAL_TOOL_NAMES.add(fn.__name__)
    fn._is_global_tool = True
    return fn


def is_global_tool_name(name: str) -> bool:
    """外部查询接口"""
    return name in _GLOBAL_TOOL_NAMES
