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
from service_mcp.utils.enums import AbnormalType, ProductCategory


# ================================================================
# Product
# ================================================================


class ProductBase(ProductValidators, BaseModel):
    """商品基本信息（示例实体，与 backend/frontend demo 契约对齐）"""

    code: str = Field(..., title="业务编码", max_length=50)
    name: str = Field(..., title="商品名称", max_length=200)
    category: ProductCategory = Field(default=ProductCategory.GOODS, title="品类")
    price: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2, title="售价")
    stock: int = Field(default=0, ge=0, title="库存")
    is_active: bool = Field(default=True, title="是否上架")
    remark: str | None = Field(default=None, title="备注")


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductValidators, BaseModel):
    """更新商品 — 全部字段可选，None 字段不更新。`code` 是对外契约，创建后不可改。"""

    code: str | None = Field(default=None, max_length=50, description="业务编码（定位用，不改值）")
    name: str | None = Field(default=None, max_length=200, description="商品名称")
    category: ProductCategory | None = Field(default=None, description="品类")
    price: Decimal | None = Field(
        default=None, max_digits=12, decimal_places=2, description="售价"
    )
    stock: int | None = Field(default=None, ge=0, description="库存")
    is_active: bool | None = Field(default=None, description="是否上架")
    remark: str | None = Field(default=None, description="备注")


class ProductDelete(BaseDeleteModel):
    """删除商品 — 通过 record_id、code 或 name 定位记录"""

    code: str | None = Field(default=None, max_length=50, description="业务编码")
    name: str | None = Field(default=None, max_length=200, description="商品名称")

    @field_validator("code", "name")
    @classmethod
    def _strip_lookup(cls, v: str | None) -> str | None:
        return super()._strip_lookup(v)

    @model_validator(mode="after")
    def _validate_delete_lookup(self) -> ProductDelete:
        if self.record_id is None and self.code is None and self.name is None:
            raise ValueError(
                "至少需要提供 record_id、code 或 name 之一来定位要删除的记录"
            )
        return self


class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime
    abnormal: AbnormalType | None = None
    is_deleted: bool = False

    model_config = ConfigDict(from_attributes=True)


# ================================================================
# ProductPrice
# ================================================================


class ProductPriceBase(ProductPriceValidators, BaseModel):
    """商品价格快照（示例实体：FK code 解析 + 复合唯一键演示）"""

    code: str = Field(..., max_length=50, description="商品业务编码（解析为内部 product_id）")
    price_date: str = Field(..., description="价格日期")
    price: Decimal = Field(..., max_digits=12, decimal_places=2, description="售价")


class ProductPriceCreate(ProductPriceBase):
    # extra=allow：占位自动创建时可透传 Product 列（如 name）作为占位商品名称
    model_config = ConfigDict(extra="allow")


class ProductPriceUpdate(ProductPriceValidators, BaseModel):
    code: str | None = Field(None, max_length=50, description="商品业务编码")
    price_date: str | None = Field(None, description="价格日期")
    price: Decimal | None = Field(None, max_digits=12, decimal_places=2, description="售价")


class ProductPriceDelete(BaseDeleteModel):
    """删除商品价格 — 通过 record_id，或 code + price_date 定位记录"""

    code: str | None = Field(default=None, max_length=50, description="商品业务编码")
    price_date: str | None = Field(default=None, description="价格日期")

    @field_validator("code")
    @classmethod
    def _strip_lookup(cls, v: str | None) -> str | None:
        return super()._strip_lookup(v)

    @model_validator(mode="after")
    def _validate_delete_lookup(self) -> ProductPriceDelete:
        if self.record_id is None and (self.code is None or self.price_date is None):
            raise ValueError(
                "至少需要提供 record_id，或同时提供 code 和 price_date 来定位要删除的记录"
            )
        return self


class ProductPriceResponse(ProductPriceBase):
    id: int
    created_at: datetime
    product_id: int | None = None
    version: int = 0
    abnormal: AbnormalType | None = None

    model_config = ConfigDict(from_attributes=True)
