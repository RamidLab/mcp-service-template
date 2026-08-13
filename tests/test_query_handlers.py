"""QueryHandler 测试：分页过滤、关键字、外键显示展开、搜索类、异常待办聚合。"""

from datetime import date

from service_mcp.handlers.query_handlers import QueryHandler
from service_mcp.models.orm import Product, ProductPrice
from service_mcp.models.pydantic.filter import ProductFilter, ProductPriceFilter
from service_mcp.models.pydantic.search import (
    ProductPriceSearchByKeyword,
    ProductSearchByFields,
    ProductSearchByKeyword,
)
from service_mcp.models.schemas import PaginationParams
from service_mcp.utils.enums import AbnormalType, Errcode, ProductDataSource
from tests.conftest import HANDLER_DB_NAME, response_data


async def test_query_product_pagination(handler_db, seeded_product):
    """分页查询返回正确结构与总数。"""
    handler = QueryHandler()
    resp = await handler.handle(
        Product, PaginationParams(page=1, page_size=10), None, HANDLER_DB_NAME
    )
    assert resp.code == Errcode.SUCCESS
    data = response_data(resp)
    assert data.pagination.total == 1
    assert len(data.items) == 1
    assert data.items[0]["product_code"] == "P0001"


async def test_query_product_keyword(handler_db, seeded_product):
    """ProductFilter.keyword 跨字段模糊匹配。"""
    filter_ = ProductFilter(keyword="测试")
    handler = QueryHandler()
    resp = await handler.handle(
        Product, PaginationParams(page=1, page_size=10), filter_, HANDLER_DB_NAME
    )
    assert response_data(resp).pagination.total == 1

    filter_none = ProductFilter(keyword="不存在的关键字")
    resp2 = await handler.handle(
        Product, PaginationParams(page=1, page_size=10), filter_none, HANDLER_DB_NAME
    )
    assert response_data(resp2).pagination.total == 0


async def test_query_product_sort(handler_db, seeded_product):
    """Filter 排序字段生效。"""
    await handler_db.insert(
        Product(
            product_code="P0300",
            product_name="排序产品",
            launch_date=date(2020, 1, 1),
            data_source=ProductDataSource.ManualImport,
        )
    )
    filter_ = ProductFilter(sort_by="launch_date", sort_order="desc")
    handler = QueryHandler()
    resp = await handler.handle(
        Product, PaginationParams(page=1, page_size=10), filter_, HANDLER_DB_NAME
    )
    # launch_date 2024 > 2020，降序第一应为 seeded_product
    assert response_data(resp).items[0]["product_code"] == "P0001"


async def test_query_price_fk_display(handler_db, seeded_product, seeded_price):
    """ProductPrice 列表展开 product_id → product_name/product_code。"""
    filter_ = ProductPriceFilter.model_validate({"product_code": "P0001"})
    handler = QueryHandler()
    resp = await handler.handle(
        ProductPrice, PaginationParams(page=1, page_size=10), filter_, HANDLER_DB_NAME
    )
    assert resp.code == Errcode.SUCCESS
    item = response_data(resp).items[0]
    assert "product_id" not in item  # 外键列被替换移除
    assert item["product_name"] == "测试产品"
    assert item["product_code"] == "P0001"
    assert str(item["price_date"]) == "2026-06-01"


async def test_search_by_keyword(handler_db, seeded_product):
    handler = QueryHandler()
    resp = await handler.handle(
        Product,
        PaginationParams(page=1, page_size=10),
        ProductSearchByKeyword(keyword="测试"),
        HANDLER_DB_NAME,
    )
    assert resp.code == Errcode.SUCCESS
    assert response_data(resp).pagination.total == 1


async def test_search_by_fields(handler_db, seeded_product):
    handler = QueryHandler()
    resp = await handler.handle(
        Product,
        PaginationParams(page=1, page_size=10),
        ProductSearchByFields.model_validate({"fields": [{"field": "product_name", "value": "测试产品"}]}),
        HANDLER_DB_NAME,
    )
    assert resp.code == Errcode.SUCCESS
    assert response_data(resp).pagination.total == 1


async def test_search_price_by_product_code(handler_db, seeded_product, seeded_price):
    """价格搜索支持通过关系字段（产品代码/名称）匹配。"""
    handler = QueryHandler()
    resp = await handler.handle(
        ProductPrice,
        PaginationParams(page=1, page_size=10),
        ProductPriceSearchByKeyword(keyword="P0001"),
        HANDLER_DB_NAME,
    )
    assert resp.code == Errcode.SUCCESS
    assert response_data(resp).pagination.total == 1


async def test_review_abnormal_items(handler_db, seeded_product, seeded_price):
    """异常待办聚合：占位产品 + 孤儿价格均出现在清单中。"""
    # 占位产品
    await handler_db.insert(
        Product(
            product_code="P9999",
            product_name="占位产品",
            abnormal=AbnormalType.Placeholder,
            data_source=ProductDataSource.ManualImport,
        )
    )
    # 孤儿价格
    await handler_db.update_by_id(
        ProductPrice, seeded_price.id, {"abnormal": AbnormalType.Orphaned}
    )

    handler = QueryHandler()
    resp = await handler.review_abnormal_items(
        PaginationParams(page=1, page_size=50), db_name=HANDLER_DB_NAME
    )
    assert resp.code == Errcode.SUCCESS
    sources = {item["source_table"] for item in response_data(resp).items}
    assert "product" in sources
    assert "product_price" in sources

    # 按来源表筛选
    resp_p = await handler.review_abnormal_items(
        PaginationParams(page=1, page_size=50),
        source_table="product_price",
        db_name=HANDLER_DB_NAME,
    )
    assert all(
        item["source_table"] == "product_price" for item in response_data(resp_p).items
    )
