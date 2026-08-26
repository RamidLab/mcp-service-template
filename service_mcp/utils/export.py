"""CSV 导出助手。

统一处理：
- Excel 兼容 BOM 头（防止中文乱码）
- date/datetime → YYYY-MM-DD、None → 空串

用法：
    csv_text = rows_to_csv(["id", "name"], [[1, "产品A"], [2, None]])
"""

__all__ = ["csv_bom", "rows_to_csv"]

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from service_mcp.utils.common import date_to_str


def csv_bom() -> str:
    """Excel 兼容 BOM 头，防止中文乱码。"""
    return chr(0xFEFF)


def rows_to_csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """将表头与行数据渲染为带 BOM 的 CSV 字符串。

    Args:
        header: 表头列名。
        rows: 行数据；date/datetime 自动格式化为 YYYY-MM-DD，None 渲染为空串。

    Returns:
        CSV 字符串（已含 BOM）。
    """
    output = io.StringIO()
    output.write(csv_bom())
    writer = csv.writer(output)
    writer.writerow(list(header))
    for row in rows:
        writer.writerow(
            [
                date_to_str(c) if isinstance(c, (date, datetime)) else ("" if c is None else c)
                for c in row
            ]
        )
    return output.getvalue()
