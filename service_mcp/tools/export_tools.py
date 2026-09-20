"""CSV 导出工具。

用统一的 rows_to_csv 助手渲染带 BOM 的 CSV 字符串，Excel 直接打开不乱码；
过滤条件复用动态 Filter（ProductFilter），与列表查询语义保持一致。
"""

__all__ = ["export_products_csv"]


from typing import Any

from fastmcp.tools import tool
from sqlalchemy import select

from service_mcp.auth.decorator import mcp_perm
from service_mcp.db.core import get_db_manager
from service_mcp.models.common import UtilResponse
from service_mcp.models.orm import Product
from service_mcp.models.pydantic.filter import ProductFilter
from service_mcp.tools.annotations import READ_ONLY
from service_mcp.utils.enums import BaseEnum, Errcode, ProductCategory
from service_mcp.utils.export import rows_to_csv


def _label(enum_cls: type[BaseEnum], value: Any) -> Any:
    """枚举值 → 中文 label；None → 空串；无法识别原样返回。"""
    if value is None:
        return ""
    if isinstance(value, enum_cls):
        return value.label
    member = enum_cls.from_value(value)
    return member.label if member is not None else value


@tool(
    name="export_products_csv",
    title="导出商品 CSV",
    description="按条件导出商品列表为 CSV 字符串（带 BOM，Excel 打开不乱码）",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="01", action="08")
async def export_products_csv(
    code: str | None = None,
    name: str | None = None,
    category: int | None = None,
    is_active: bool | None = None,
    db_name: str = "default",
) -> UtilResponse[str]:
    """导出商品列表 CSV"""
    mgr = await get_db_manager(db_name)

    filters = ProductFilter(
        code=code,
        name=name,
        category=category,
        is_active=is_active,
    )
    stmt = (
        select(
            Product.id,
            Product.code,
            Product.name,
            Product.category,
            Product.price,
            Product.stock,
            Product.is_active,
            Product.remark,
            Product.updated_at,
        )
        .where(*filters.to_where())
        .order_by(Product.id)
        .limit(10000)
    )
    rows = await mgr.fetch_all(stmt, {})

    header = [
        "id",
        "code",
        "name",
        "category",
        "price",
        "stock",
        "is_active",
        "remark",
        "updated_at",
    ]
    data = []
    for r in rows:
        data.append(
            [
                r["id"],
                r["code"],
                r["name"],
                _label(ProductCategory, r["category"]),
                r["price"],
                r["stock"],
                r["is_active"],
                r.get("remark") or "",
                r.get("updated_at"),
            ]
        )
    return UtilResponse(code=Errcode.SUCCESS, message="导出成功", data=rows_to_csv(header, data))
