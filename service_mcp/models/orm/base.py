__all__ = ["Base", "EnumInt"]

from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class EnumInt(TypeDecorator):
    """枚举 ↔ 整数 列类型：绑定枚举对象时存其 value，读取时还原为枚举成员。

    用于将纯 Enum（不继承 int）映射到 Integer 列，调用方无需关心 .value 转换。
    """

    impl = Integer
    cache_ok = True

    def __init__(self, enum_cls: type[Enum]) -> None:
        self.enum_cls: type[Enum] = enum_cls
        super().__init__()

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, self.enum_cls):
            # enum_cls 是动态枚举类型，isinstance 收窄后 value 为 Enum 成员；
            # 枚举 value 本身即 int（EnumInt 仅用于整数值枚举）
            return value.value
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return self.enum_cls(value)


class Base(DeclarativeBase):
    """基础模型类"""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    created_by: Mapped[str | None] = mapped_column(
        String(50), default=None, comment="创建者用户ID，用于数据范围控制"
    )
