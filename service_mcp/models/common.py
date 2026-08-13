__all__ = ["UtilResponse"]

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class UtilResponse(BaseModel, Generic[T]):
    """
    统一接口返回格式的数据模型。

    用于封装 API 响应的标准结构，包含状态码、消息和实际数据。
    继承自 Pydantic 的 BaseModel，自动提供数据验证和序列化功能。

    Attributes:
        code (int): 响应状态码，如其他自定义状态码。
        message (str): 对状态码的文本说明，如“成功”或错误详情。
        data (Optional[Any]): 实际返回的数据负载，可为 None 或任意 JSON 可序列化对象。
    """

    code: int | Enum
    message: str
    data: T | None = None
