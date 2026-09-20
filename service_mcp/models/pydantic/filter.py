__all__ = ["ProductFilter", "ProductPriceFilter"]

from typing import Literal

from pydantic import Field
from sqlalchemy import or_

from service_mcp.models.orm import Product, ProductPrice
from service_mcp.models.pydantic import BaseFilter
from service_mcp.models.pydantic.builder import create_filter_class
from service_mcp.models.pydantic.generate import register_pyi_class


_ProductFilterBase = create_filter_class(
    model=Product,
    exclude=["id", "is_deleted"],
    extra_fields={
        "keyword": (
            str | None,
            Field(
                default=None,
                title="关键字搜索",
                description="模糊匹配业务编码、商品名称",
            ),
        ),
        "sort_by": (
            Literal[
                "code",
                "name",
                "price",
                "stock",
                "created_at",
                "updated_at",
            ]
            | None,
            Field(
                default=None,
                title="排序字段",
                description="排序字段，可在 sort_order 字段选择升降序(asc,desc)",
            ),
        ),
        "sort_order": (
            Literal["asc", "desc"],
            Field(default="asc", title="排序方向", description="排序方向"),
        ),
    },
)


class ProductFilter(_ProductFilterBase):
    """扩展 ProductFilter，支持 keyword 跨字段模糊搜索。"""

    def to_where(self):
        conditions = super().to_where()
        kw = getattr(self, "keyword", None)
        if isinstance(kw, str) and kw:
            pattern = f"%{kw}%"
            conditions.append(
                or_(
                    Product.code.like(pattern),
                    Product.name.like(pattern),
                )
            )
        return conditions


# 显式 class 声明需重新登记，让 stub 生成器输出完整 class stub（含 to_where 签名）；
# base 统一传 BaseFilter 与动态注册保持一致（stub 只做类型提示，不反映真实基类链）
register_pyi_class("ProductFilter", BaseFilter, "filter", cls=ProductFilter, explicit=True)


ProductPriceFilter = create_filter_class(
    model=ProductPrice,
    exclude=["id", "product_id", "version"],
    column_mappings={
        "code": (ProductPrice.product, Product.code, str | None),
        "name": (ProductPrice.product, Product.name, str | None),
    },
    extra_fields={
        "sort_by": (
            Literal[
                "price_date",
                "price",
                "created_at",
                "updated_at",
            ]
            | None,
            Field(default=None, title="排序字段", description="排序字段"),
        ),
        "sort_order": (
            Literal["asc", "desc"],
            Field(default="asc", title="排序方向", description="排序方向"),
        ),
    },
)
