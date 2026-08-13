from __future__ import annotations


__all__ = [
    "ProductBase",
    "ProductCreate",
    "ProductDelete",
    "ProductPriceBase",
    "ProductPriceCreate",
    "ProductPriceDelete",
    "ProductPriceResponse",
    "ProductPriceUpdate",
    "ProductResponse",
    "ProductUpdate",
]

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from service_mcp.models.pydantic import BaseDeleteModel
from service_mcp.models.pydantic.product_validators import ProductPriceValidators, ProductValidators
from service_mcp.utils.enums import AbnormalType, ProductDataSource, ProductStatus, ProductType


# ================================================================
# Product
# ================================================================


class ProductBase(ProductValidators, BaseModel):
    """产品基本信息（示例实体）"""

    product_code: str = Field(..., title="产品代码", max_length=20)
    product_name: str = Field(..., title="产品名称", max_length=200)
    product_short_name: str | None = Field(default=None, title="产品简称", max_length=100)
    product_type: ProductType | None = Field(default=ProductType.Unknown, title="产品类型")
    status: ProductStatus | None = Field(default=ProductStatus.Unknown, title="产品状态")
    launch_date: str | None = Field(default=None, title="成立/上市日期")
    data_source: ProductDataSource = Field(default=ProductDataSource.ManualImport, title="数据来源")


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductValidators, BaseModel):
    """更新产品 — 全部字段可选，None 字段不更新"""

    product_code: str | None = Field(default=None, max_length=20, description="产品代码")
    product_name: str | None = Field(default=None, max_length=200, description="产品名称")
    product_short_name: str | None = Field(default=None, max_length=100, description="产品简称")
    product_type: ProductType | None = Field(default=None, description="产品类型")
    status: ProductStatus | None = Field(default=None, description="产品状态")
    launch_date: str | None = Field(default=None, description="成立/上市日期")
    data_source: ProductDataSource | None = Field(default=None, description="数据来源")


class ProductDelete(BaseDeleteModel):
    """删除产品 — 通过 record_id、product_code 或 product_name 定位记录"""

    product_code: str | None = Field(default=None, max_length=20, description="产品代码")
    product_name: str | None = Field(default=None, max_length=200, description="产品名称")

    @field_validator("product_code", "product_name")
    @classmethod
    def _strip_lookup(cls, v: str | None) -> str | None:
        return super()._strip_lookup(v)

    @model_validator(mode="after")
    def _validate_delete_lookup(self) -> ProductDelete:
        if self.record_id is None and self.product_code is None and self.product_name is None:
            raise ValueError(
                "至少需要提供 record_id、product_code 或 product_name 之一来定位要删除的记录"
            )
        return self


class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime
    abnormal: AbnormalType | None = None

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# ProductPrice
# ================================================================


class ProductPriceBase(ProductPriceValidators, BaseModel):
    """产品价格信息（示例实体：FK code 解析 + 复合唯一键演示）"""

    product_code: str = Field(..., max_length=20, description="产品代码")
    price_date: str = Field(..., description="价格日期")
    unit_price: Decimal = Field(..., max_digits=12, decimal_places=4, description="单位价格")
    acc_price: Decimal | None = Field(None, max_digits=12, decimal_places=4, description="累计价格")
    daily_return_rate: Decimal | None = Field(
        None, max_digits=10, decimal_places=4, description="日涨跌幅"
    )
    data_source: ProductDataSource = Field(..., description="数据来源")


class ProductPriceCreate(ProductPriceBase):
    model_config = ConfigDict(extra="allow")


class ProductPriceUpdate(ProductPriceValidators, BaseModel):
    product_code: str | None = Field(None, max_length=20, description="产品代码")
    price_date: str | None = Field(None, description="价格日期")
    unit_price: Decimal | None = Field(
        None, max_digits=12, decimal_places=4, description="单位价格"
    )
    acc_price: Decimal | None = Field(None, max_digits=12, decimal_places=4, description="累计价格")
    daily_return_rate: Decimal | None = Field(
        None, max_digits=10, decimal_places=4, description="日涨跌幅"
    )
    data_source: ProductDataSource | None = Field(None, description="数据来源")


class ProductPriceDelete(BaseDeleteModel):
    """删除产品价格 — 通过 record_id，或 product_code + price_date 定位记录"""

    product_code: str | None = Field(default=None, max_length=20, description="产品代码")
    price_date: str | None = Field(default=None, description="价格日期")

    @field_validator("product_code")
    @classmethod
    def _strip_lookup(cls, v: str | None) -> str | None:
        return super()._strip_lookup(v)

    @model_validator(mode="after")
    def _validate_delete_lookup(self) -> ProductPriceDelete:
        if self.record_id is None and (self.product_code is None or self.price_date is None):
            raise ValueError(
                "至少需要提供 record_id，或同时提供 product_code 和 price_date 来定位要删除的记录"
            )
        return self


class ProductPriceResponse(ProductPriceBase):
    id: int
    created_at: datetime
    product_id: int | None = None
    version: int = 0
    abnormal: AbnormalType | None = None

    model_config = ConfigDict(from_attributes=True)
