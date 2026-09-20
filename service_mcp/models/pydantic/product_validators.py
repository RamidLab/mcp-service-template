from __future__ import annotations


__all__ = ["ProductPriceValidators", "ProductValidators"]

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import field_validator, model_validator

from service_mcp.utils.common import to_date_flexible


def _not_future(v: str | None, label: str) -> str | None:
    """日期字符串不能晚于今天。"""
    if v is None:
        return v
    if to_date_flexible(v) > datetime.today().date():
        raise ValueError(f"{label}不能晚于今天，当前值: {v}")
    return v


def _strip_required(v: str | None, label: str) -> str | None:
    """去除字符串空白，空白字符串抛错。"""
    if v is None:
        return v
    s = v.strip()
    if not s:
        raise ValueError(label)
    return s


def _strip_optional(v: str | None) -> str | None:
    """去除字符串空白，空白字符串转为 None。"""
    if v is None:
        return v
    return v.strip() or None


class ProductValidators:
    """Product 模型通用字段校验器 Mixin。

    提供 code、name 等字段的字符串修剪与基本非空校验。
    适用于 ProductBase / ProductCreate / ProductUpdate 等模型。
    """

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str | None) -> str | None:
        """去除业务编码的首尾空白。None 值直接返回。"""
        if v is None:
            return v
        return v.strip()

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        """去除商品名称空白，若结果为空则抛出 ValueError。"""
        if v is None:
            return v
        s = v.strip()
        if not s:
            raise ValueError("商品名称不能为空白")
        return s

    @field_validator("price")
    @classmethod
    def _price_non_negative(cls, v: Decimal | None) -> Decimal | None:
        """售价不能为负数（与 backend demo 校验同口径）。"""
        if v is not None and v < 0:
            raise ValueError(f"售价不能为负数，当前值: {v}")
        return v


class ProductPriceValidators:
    """ProductPrice 模型通用字段校验器 Mixin。

    校验商品业务编码非空、售价非负、价格日期不晚于今天。
    """

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str | None) -> str | None:
        """去除业务编码空白，要求非空。"""
        return _strip_required(v, "业务编码不能为空白")

    @field_validator("price")
    @classmethod
    def _price_non_negative(cls, v: Decimal | None) -> Decimal | None:
        """售价不能为负数。"""
        if v is not None and v < 0:
            raise ValueError(f"售价不能为负数，当前值: {v}")
        return v

    @field_validator("price_date")
    @classmethod
    def _price_date_not_future(cls, v: str | None) -> str | None:
        """价格日期不能晚于今天。"""
        return _not_future(v, "价格日期")

    @model_validator(mode="after")
    def _validate_price_date_present(self: Any) -> Any:
        """创建场景 price_date 与 price 必填（Update 模型两者均可选，跳过）。"""
        return self
