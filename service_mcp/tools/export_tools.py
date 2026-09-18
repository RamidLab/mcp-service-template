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
from service_mcp.utils.enums import BaseEnum, Errcode, ProductDataSource, ProductStatus, ProductType
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
    title="导出产品 CSV",
    description="按条件导出产品列表为 CSV 字符串（带 BOM，Excel 打开不乱码）",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="01", action="08")
async def export_products_csv(
    product_name: str | None = None,
    product_code: str | None = None,
    product_type: int | None = None,
    status: int | None = None,
    db_name: str = "default",
) -> UtilResponse[str]:
    """导出产品列表 CSV"""
    mgr = await get_db_manager(db_name)

    filters = ProductFilter(
        product_name=product_name,
        product_code=product_code,
        product_type=product_type,
        status=status,
    )
    stmt = (
        select(
            Product.id,
            Product.product_code,
            Product.product_name,
            Product.product_short_name,
            Product.product_type,
            Product.status,
            Product.launch_date,
            Product.data_source,
            Product.updated_at,
        )
        .where(*filters.to_where())
        .order_by(Product.id)
        .limit(10000)
    )
    rows = await mgr.fetch_all(stmt, {})

    header = [
        "id",
        "product_code",
        "product_name",
        "product_short_name",
        "product_type",
        "status",
        "launch_date",
        "data_source",
        "updated_at",
    ]
    data = []
    for r in rows:
        data.append(
            [
                r["id"],
                r["product_code"],
                r["product_name"],
                r.get("product_short_name") or "",
                _label(ProductType, r["product_type"]),
                _label(ProductStatus, r["status"]),
                r.get("launch_date"),
                _label(ProductDataSource, r["data_source"]),
                r.get("updated_at"),
            ]
        )
    return UtilResponse(code=Errcode.SUCCESS, message="导出成功", data=rows_to_csv(header, data))
