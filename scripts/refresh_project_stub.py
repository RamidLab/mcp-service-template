"""重新生成项目自身的 .pyi 类型存根文件。

清空注册表后重新加载 filter 和 search 模块，
触发动态创建的过滤器/搜索类重新生成 .pyi 存根。

用法: .venv/Scripts/python scripts/refresh_project_stub.py
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


STUBS = [
    Path(__file__).parent.parent / "service_mcp" / "models" / "pydantic" / "filter.pyi",
    Path(__file__).parent.parent / "service_mcp" / "models" / "pydantic" / "search.pyi",
]


def refresh() -> None:
    from service_mcp.models.pydantic.generate import clean_registry

    clean_registry()

    import service_mcp.models.pydantic.filter as filter_mod
    import service_mcp.models.pydantic.search as search_mod

    importlib.reload(search_mod)
    importlib.reload(filter_mod)
    print("[stub] pyi 已更新。")


def format_stubs() -> None:
    for stub in STUBS:
        if stub.exists():
            # 仅 ruff check --fix（修复排序/未用导入）；
            # 不跑 ruff format——它会把 .pyi 的导入合并成单行，破坏 isort/PyCharm 期望的分组
            subprocess.run(
                [sys.executable, "-m", "ruff", "check", "--fix", str(stub)],
                capture_output=True,
            )


if __name__ == "__main__":
    refresh()
    format_stubs()
    print("[stub] 格式化完成。")
