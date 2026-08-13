__all__ = ["check_result", "date_to_str", "to_date_flexible"]

from datetime import date, datetime
from typing import Any, TypeVar

from dateutil import parser

from service_mcp.models.common import UtilResponse
from service_mcp.utils.enums import Errcode


T = TypeVar("T")


def check_result(result: UtilResponse[T]) -> UtilResponse[T]:
    """
    检查结果是否成功

    Args:
        result: API 调用结果

    Returns:
        通用响应
    """
    if result.code not in {Errcode.SUCCESS, Errcode.DONE, Errcode.CONTINUE, Errcode.PROCESS}:
        raise Exception(result.message)
    return result


def to_date_flexible(
    date_str: str, day_first: bool = False, year_first: bool = False, fuzzy: bool = False
) -> date:
    """
    将各种常见日期字符串解析为 datetime.date 对象。

    Args:
        date_str: 日期字符串，如 '20260510', '2026-05-10', '10/05/2026' 等。
        day_first: 针对 '10/05/2026' 这种歧义格式，若为 True 则按“日/月/年”解析。
        year_first: 若为 True 则优先将前面的数字视为年份。
        fuzzy: 是否允许解析不完全的日期字符串。

    Returns:
        datetime.date 对象，如果解析失败则抛出 ValueError。
    """
    dt = parser.parse(date_str, dayfirst=day_first, yearfirst=year_first, fuzzy=fuzzy)
    return dt.date()


def date_to_str(d: Any) -> str:
    """将 date/datetime 转为 YYYY-MM-DD 字符串"""
    if d is None:
        return ""
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    return str(d)
