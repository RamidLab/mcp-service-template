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

    提供 product_code、product_name 等字段的字符串修剪与基本非空校验。
    适用于 ProductBase / ProductCreate / ProductUpdate 等模型。
    """

    @field_validator("product_code")
    @classmethod
    def _strip_product_code(cls, v: str | None) -> str | None:
        """去除产品代码的首尾空白。None 值直接返回。"""
        if v is None:
            return v
        return v.strip()

    @field_validator("product_name", "product_short_name")
    @classmethod
    def _strip_product_name(cls, v: str | None) -> str | None:
        """去除产品名称/简称的空白，若结果为空则抛出 ValueError。"""
        if v is None:
            return v
        s = v.strip()
        if not s:
            raise ValueError("产品名称不能为空白")
        return s


class ProductPriceValidators:
    """ProductPrice 模型通用字段校验器 Mixin。

    校验产品代码非空、单位价格为正、价格日期不晚于今天，
    并检查累计价格与单位价格的大小关系。
    """

    @field_validator("product_code")
    @classmethod
    def _strip_product_code(cls, v: str | None) -> str | None:
        """去除产品代码空白，要求非空。"""
        return _strip_required(v, "产品代码不能为空白")

    @field_validator("unit_price")
    @classmethod
    def _positive_unit_price(cls, v: Decimal | None) -> Decimal | None:
        """单位价格必须大于 0。"""
        if v is not None and v <= 0:
            raise ValueError(f"单位价格必须大于0，当前值: {v}")
        return v

    @field_validator("acc_price")
    @classmethod
    def _zero_to_none(cls, v: Decimal | None) -> Decimal | None:
        """累计价格为 0 时视为未提供，转为 None。"""
        if v is not None and v == Decimal(0):
            return None
        return v

    @field_validator("price_date")
    @classmethod
    def _price_date_not_future(cls, v: str | None) -> str | None:
        """价格日期不能晚于今天。"""
        return _not_future(v, "价格日期")

    @model_validator(mode="after")
    def _validate_price_consistency(self: Any) -> Any:
        """若同时提供了累计价格与单位价格，则累计价格不得小于单位价格。"""
        acc = self.acc_price
        unit = self.unit_price
        if acc is not None and unit is not None and acc < unit:
            raise ValueError(f"累计价格 ({acc}) 不能小于单位价格 ({unit})")
        return self
