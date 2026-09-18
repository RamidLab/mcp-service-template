__all__ = [
    "get_product_enums",
    "get_product_id_by_code",
    "get_product_list",
    "get_product_price_list",
    "search_product_price_by_fields",
    "search_product_price_by_keyword",
    "search_products_by_fields",
    "search_products_by_keyword",
]


from enum import Enum
from typing import Any

from fastmcp.tools import tool
from sqlalchemy import select

from service_mcp.auth.decorator import mcp_perm
from service_mcp.db.core import get_db_manager
from service_mcp.handlers.query_handlers import QueryHandler
from service_mcp.models.common import UtilResponse
from service_mcp.models.orm import Product, ProductPrice
from service_mcp.models.orm.base import Base
from service_mcp.models.pydantic import BaseFilter, BaseSearchByFields, BaseSearchByKeyword
from service_mcp.models.pydantic.filter import ProductFilter, ProductPriceFilter
from service_mcp.models.pydantic.search import (
    ProductPriceSearchByFields,
    ProductPriceSearchByKeyword,
    ProductSearchByFields,
    ProductSearchByKeyword,
)
from service_mcp.models.schemas import PageData, PaginationParams
from service_mcp.tools.annotations import READ_ONLY
from service_mcp.utils.enums import Errcode, ProductDataSource, ProductStatus, ProductType


async def _handle_query(
    model: type[Base],
    params: PaginationParams,
    filter_or_search: BaseFilter | BaseSearchByKeyword | BaseSearchByFields | None,
    db_name: str = "default",
) -> UtilResponse[PageData]:
    """统一创建 Handler 并执行查询"""
    handler = QueryHandler()
    return await handler.handle(model, params, filter_or_search, db_name)


def _enum_options(enum_cls: type[Enum], label_fn=None) -> list[dict[str, Any]]:
    """将枚举转为前端下拉选项 [{value, label}, ...]。

    Args:
        enum_cls: 枚举类
        label_fn: 可选的自定义 label 函数（默认取成员 .label 属性）
    """
    return [
        {"value": s.value, "label": label_fn(s) if label_fn else getattr(s, "label", str(s.value))}
        for s in enum_cls.__members__.values()
    ]


# ═══════════════════════════════════════════════════════════
#  列表查询
# ═══════════════════════════════════════════════════════════


@tool(
    name="get_product_list",
    title="产品列表",
    description="分页查询产品列表，支持产品代码/名称/简称关键字模糊搜索及多字段过滤",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="01", action="01")
async def get_product_list(
    params: PaginationParams,
    filters: ProductFilter | None = None,
    db_name: str = "default",
) -> UtilResponse[PageData]:
    """查询产品列表"""
    return await _handle_query(Product, params, filters, db_name)


@tool(
    name="get_product_price_list",
    title="产品价格列表",
    description="分页查询产品价格列表，支持按产品代码/名称、日期、来源过滤",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="02", action="01")
async def get_product_price_list(
    params: PaginationParams,
    filters: ProductPriceFilter | None = None,
    db_name: str = "default",
) -> UtilResponse[PageData]:
    """查询产品价格列表"""
    return await _handle_query(ProductPrice, params, filters, db_name)


# ═══════════════════════════════════════════════════════════
#  搜索
# ═══════════════════════════════════════════════════════════


@tool(
    name="search_products_by_keyword",
    title="产品关键字搜索",
    description="按关键字模糊搜索产品（匹配代码/名称/简称）",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="01", action="08")
async def search_products_by_keyword(
    search: ProductSearchByKeyword,
    params: PaginationParams,
    db_name: str = "default",
) -> UtilResponse[PageData]:
    """产品关键字搜索"""
    return await _handle_query(Product, params, search, db_name)


@tool(
    name="search_products_by_fields",
    title="产品字段搜索",
    description="按字段精确/模糊组合搜索产品（支持 and/or 逻辑与分组）",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="01", action="08")
async def search_products_by_fields(
    search: ProductSearchByFields,
    params: PaginationParams,
    db_name: str = "default",
) -> UtilResponse[PageData]:
    """产品字段搜索"""
    return await _handle_query(Product, params, search, db_name)


@tool(
    name="search_product_price_by_keyword",
    title="产品价格关键字搜索",
    description="按关键字搜索产品价格（匹配产品代码/名称）",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="02", action="08")
async def search_product_price_by_keyword(
    search: ProductPriceSearchByKeyword,
    params: PaginationParams,
    db_name: str = "default",
) -> UtilResponse[PageData]:
    """产品价格关键字搜索"""
    return await _handle_query(ProductPrice, params, search, db_name)


@tool(
    name="search_product_price_by_fields",
    title="产品价格字段搜索",
    description="按字段精确/模糊组合搜索产品价格（支持 and/or 逻辑与分组）",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="02", action="08")
async def search_product_price_by_fields(
    search: ProductPriceSearchByFields,
    params: PaginationParams,
    db_name: str = "default",
) -> UtilResponse[PageData]:
    """产品价格字段搜索"""
    return await _handle_query(ProductPrice, params, search, db_name)


# ═══════════════════════════════════════════════════════════
#  枚举与便捷查询
# ═══════════════════════════════════════════════════════════


@tool(
    name="get_product_enums",
    title="产品枚举字典",
    description="获取产品相关的枚举字典（状态、类型、数据来源），用于前端下拉选项",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="01", action="01")
async def get_product_enums() -> UtilResponse[dict[str, Any]]:
    """产品枚举字典"""
    data = {
        "product_status": _enum_options(ProductStatus),
        "product_type": _enum_options(ProductType),
        "product_data_source": _enum_options(ProductDataSource),
    }
    return UtilResponse(code=0, message="查询成功", data=data)


@tool(
    name="get_product_id_by_code",
    title="产品代码转 ID",
    description="根据产品代码查询内部记录 ID（占位记录同样可查到）",
    tags={"domain_tool"},
    annotations=READ_ONLY,
)
@mcp_perm(resource="01", action="02")
async def get_product_id_by_code(
    product_code: str,
    db_name: str = "default",
) -> UtilResponse[dict[str, Any]]:
    """产品代码转 ID"""
    mgr = await get_db_manager(db_name)
    row = await mgr.fetch_one(
        select(Product.id, Product.product_code, Product.product_name, Product.abnormal).where(
            Product.product_code == product_code.strip()
        )
    )
    if row is None:
        return UtilResponse(
            code=Errcode.RECORD_NOT_FOUND,
            message=f"未找到产品代码为 '{product_code}' 的记录",
            data={},
        )
    data = {
        "id": row["id"],
        "product_code": row["product_code"],
        "product_name": row["product_name"],
        "abnormal": int(row["abnormal"]) if row["abnormal"] is not None else None,
    }
    return UtilResponse(code=0, message="查询成功", data=data)
